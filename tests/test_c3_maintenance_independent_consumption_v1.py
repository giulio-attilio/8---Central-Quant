"""Offline anti-rollback protocol; independent authority is a synthetic fake."""

from dataclasses import replace
import sqlite3
from contextlib import closing

import pytest

from test_trade_registry_c3_maintenance_activation_offline_v1 import env, deny_external_access
from test_trade_registry_c3_maintenance_authority_startup_v1 import signed


def local_rows(signed):
    with closing(sqlite3.connect(signed.ledger._database)) as db:
        return db.execute("SELECT * FROM c3_maintenance_claims").fetchall()


@pytest.mark.parametrize("dependency", ["monotonic_consumer", "consumption_verifier"])
def test_missing_independent_dependency_fails_closed_before_consumption(signed, dependency):
    authority = signed.m.AuthenticatedMaintenanceAuthorizationV1(**(signed.options | {dependency: None}))
    assert authority(signed.request, signed.binding) is False
    assert not signed.consumed and local_rows(signed) == []


@pytest.mark.parametrize("field,value", [
    ("pinned_consumption_namespace_sha256", None),
    ("pinned_consumption_key_id_sha256", None),
    ("consumption_key_epoch", 0), ("consumption_key_epoch", True),
])
def test_missing_or_invalid_pins_fail_closed(signed, field, value):
    authority = signed.m.AuthenticatedMaintenanceAuthorizationV1(**(signed.options | {
        "config": replace(signed.config, **{field: value}),
    }))
    assert authority(signed.request, signed.binding) is False
    assert not signed.consumed and local_rows(signed) == []


@pytest.mark.parametrize("reply", [True, 1, None, {}, "COMMITTED"])
def test_boolean_or_unverified_response_cannot_authorize(signed, monkeypatch, reply):
    monkeypatch.setattr(signed.consumer, "consume_once", lambda **_: reply)
    assert signed.authority(signed.request, signed.binding) is False
    assert local_rows(signed) == []


@pytest.mark.parametrize("field,value", [
    ("namespace_sha256", "c" * 64), ("claim_sha256", "c" * 64),
    ("payload_sha256", "c" * 64), ("challenge_sha256", "c" * 64),
    ("deadline", 111.0), ("deadline", True), ("committed", False), ("committed", 1),
])
def test_even_signed_receipt_requires_exact_binding(signed, monkeypatch, field, value):
    original = signed.consumer.consume_once
    def altered(**kwargs):
        return signed.sign_receipt(replace(original(**kwargs), **{field: value}))
    monkeypatch.setattr(signed.consumer, "consume_once", altered)
    assert signed.authority(signed.request, signed.binding) is False
    assert local_rows(signed) == []


def test_invalid_consumption_signature_fails_closed(signed, monkeypatch):
    original = signed.consumer.consume_once
    monkeypatch.setattr(signed.consumer, "consume_once", lambda **kw: replace(original(**kw), signature_sha256="0" * 64))
    assert signed.authority(signed.request, signed.binding) is False
    assert local_rows(signed) == []


def test_receipt_signed_by_wrong_pinned_key_is_rejected(signed):
    authority = signed.m.AuthenticatedMaintenanceAuthorizationV1(**(signed.options | {
        "config": replace(signed.config, pinned_consumption_key_id_sha256=signed.config.pinned_key_id_sha256),
    }))
    assert authority(signed.request, signed.binding) is False
    assert local_rows(signed) == []


def test_randomness_failure_denies_before_independent_consumption(signed, monkeypatch):
    def unavailable(_size):
        raise OSError("synthetic entropy failure")
    monkeypatch.setattr(signed.m.os, "urandom", unavailable)
    assert signed.authority(signed.request, signed.binding) is False
    assert not signed.consumed and local_rows(signed) == []


@pytest.mark.parametrize("failure", ["lost_response", "deadline", "revocation", "clock_regression"])
def test_failure_after_independent_commit_burns_request_without_local_write(signed, monkeypatch, failure):
    original = signed.consumer.consume_once
    def interrupted(**kwargs):
        receipt = original(**kwargs)
        if failure == "lost_response":
            raise TimeoutError("synthetic response lost after commit")
        if failure == "deadline":
            signed.env.time = 110.0
        elif failure == "revocation":
            signed.revocations.revoked = True
        else:
            signed.env.time = 99.0
        return receipt
    monkeypatch.setattr(signed.consumer, "consume_once", interrupted)
    assert signed.authority(signed.request, signed.binding) is False
    assert local_rows(signed) == [] and len(signed.consumed) == 1
    signed.env.time, signed.revocations.revoked = 100.0, False
    rebuilt = signed.m.AuthenticatedMaintenanceAuthorizationV1(**(signed.options | {
        "monotonic_consumer": signed.new_consumer(),
    }))
    assert rebuilt(signed.request, signed.binding) is False


def test_failure_before_independent_commit_does_not_grant_or_write(signed, monkeypatch):
    def unavailable(**_):
        raise TimeoutError("synthetic consumer unavailable")
    monkeypatch.setattr(signed.consumer, "consume_once", unavailable)
    assert signed.authority(signed.request, signed.binding) is False
    assert not signed.consumed and local_rows(signed) == []


def test_local_commit_failure_cannot_undo_independent_consumption(signed, monkeypatch):
    original = signed.ledger.consume_once
    monkeypatch.setattr(signed.ledger, "consume_once", lambda **_: False)
    assert signed.authority(signed.request, signed.binding) is False
    assert local_rows(signed) == [] and len(signed.consumed) == 1
    monkeypatch.setattr(signed.ledger, "consume_once", original)
    assert signed.authority(signed.request, signed.binding) is False


@pytest.mark.parametrize("boundary", ["independent_commit", "before_local_commit", "after_local_commit"])
def test_simulated_crash_without_exception_recovery_cannot_reauthorize(signed, monkeypatch, boundary):
    class SimulatedCrash(BaseException):
        pass
    consumer_call = signed.consumer.consume_once
    ledger_call = signed.ledger.consume_once
    def interrupted_consumer(**kwargs):
        consumer_call(**kwargs)
        raise SimulatedCrash()
    def interrupted_ledger(**kwargs):
        if boundary == "after_local_commit":
            ledger_call(**kwargs)
        raise SimulatedCrash()
    if boundary == "independent_commit":
        monkeypatch.setattr(signed.consumer, "consume_once", interrupted_consumer)
    else:
        monkeypatch.setattr(signed.ledger, "consume_once", interrupted_ledger)
    with pytest.raises(SimulatedCrash):
        signed.authority(signed.request, signed.binding)
    assert len(signed.consumed) == 1
    assert len(local_rows(signed)) == (1 if boundary == "after_local_commit" else 0)
    ledger = signed.m.SQLiteMaintenanceAuthorizationLedgerV1(signed.ledger._database, enabled=True)
    rebuilt = signed.m.AuthenticatedMaintenanceAuthorizationV1(**(signed.options | {
        "ledger": ledger, "monotonic_consumer": signed.new_consumer(),
    }))
    assert rebuilt(signed.request, signed.binding) is False


def test_cached_signed_receipt_cannot_replay_after_restore(signed, monkeypatch):
    with closing(sqlite3.connect(":memory:")) as backup:
        with closing(sqlite3.connect(signed.ledger._database)) as db:
            db.backup(backup)
        assert signed.authority(signed.request, signed.binding) is True
        old_receipt = signed.receipts[0]
        with closing(sqlite3.connect(signed.ledger._database)) as db:
            backup.backup(db)
    monkeypatch.setattr(signed.consumer, "consume_once", lambda **_: old_receipt)
    rebuilt = signed.m.AuthenticatedMaintenanceAuthorizationV1(**signed.options)
    assert rebuilt(signed.request, signed.binding) is False
    assert local_rows(signed) == []
    assert "synthetic" not in repr(old_receipt)
    assert old_receipt.signature_sha256 not in repr(old_receipt)


def test_consumption_key_revocation_denies_before_both_consumptions(signed, monkeypatch):
    monkeypatch.setattr(signed.revocations, "root_authority_key_revoked_v2",
                        lambda **kw: kw["key_id_sha256"] == signed.config.pinned_consumption_key_id_sha256)
    assert signed.authority(signed.request, signed.binding) is False
    assert not signed.consumed and local_rows(signed) == []


def test_unavailable_independent_authority_never_reaches_maintenance(signed):
    authority = signed.m.AuthenticatedMaintenanceAuthorizationV1(**(signed.options | {"monotonic_consumer": None}))
    result = signed.env.build(consume_authorization=authority).run_offline(signed.request)
    assert result["status"] == "C3_MAINTENANCE_AUTHORIZATION_DENIED"
    assert signed.env.calls == [] and result["live_allowed"] is False
