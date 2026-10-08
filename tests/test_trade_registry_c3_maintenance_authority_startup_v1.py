"""Synthetic signing, temporary ledger and AST-extracted startup prefix only."""

import ast
import copy
import hashlib
import hmac
import importlib
import sqlite3
import sys
import threading
from contextlib import closing
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_trade_registry_c3_maintenance_activation_offline_v1 import env, deny_external_access


@pytest.fixture
def signed(env):
    module = importlib.import_module("trade_registry_c3_maintenance_authorization_v1")
    key = b"synthetic-test-key-not-a-production-secret-0001"
    key_id = hashlib.sha256(b"synthetic-key-id").hexdigest()
    consumption_key = b"synthetic-independent-consumption-key-0001"
    consumption_key_id = hashlib.sha256(b"synthetic-consumption-key-id").hexdigest()
    class Keys:
        def resolve_root_hmac_key_v2(self, *, key_id_sha256):
            return {key_id: key, consumption_key_id: consumption_key}.get(key_id_sha256)
    class Revocations:
        revoked = False
        def root_authority_key_revoked_v2(self, **_kwargs):
            return self.revoked
    keys, revocations = Keys(), Revocations()
    adapters = module.authority_adapters
    verifier = adapters.InjectedRootAuthorityVerifierV2(
        adapters.InjectedRootAuthorityVerifierConfigV2(
            enabled=True, scope_attestation=adapters.PRODUCTION_AUTHORITY_ADAPTERS_EXPLICIT_DEPENDENCY_SCOPE_V2,
            expected_key_provider_object_identity_sha256=adapters._object_identity(keys),
        ), key_provider=keys,
    )
    ledger = module.SQLiteMaintenanceAuthorizationLedgerV1(env.root / "synthetic-authorizations.sqlite", enabled=True)
    ledger.provision()
    # Reference ONLY: state is in memory outside the temporary ledger backup.
    # Production needs an authenticated, independently durable implementation.
    consumed = set()
    consumption_lock = threading.Lock()
    receipts = []
    def sign_receipt(receipt):
        digest = module.monotonic_consumption_receipt_sha256(receipt)
        return replace(receipt, signature_sha256=hmac.new(
            consumption_key, digest.encode("ascii"), hashlib.sha256,
        ).hexdigest())
    class Consumer:
        def consume_once(self, **kwargs):
            with consumption_lock:
                claim = (kwargs["namespace_sha256"], kwargs["claim_sha256"])
                if claim in consumed:
                    return None
                consumed.add(claim)
                receipt = sign_receipt(module.MonotonicConsumptionReceiptV1(
                    **kwargs, committed=True, signature_sha256="",
                ))
                receipts.append(receipt)
                return receipt
    consumer = Consumer()
    config = module.MaintenanceAuthorityConfigV1(
        enabled=True, pinned_key_id_sha256=key_id, key_epoch=1,
        pinned_storage_root_sha256=env.options["storage_root_binding_sha256"],
        pinned_ledger_storage_sha256=ledger.storage_binding_sha256(),
        pinned_consumption_namespace_sha256=hashlib.sha256(b"synthetic-stable-namespace").hexdigest(),
        pinned_consumption_key_id_sha256=consumption_key_id, consumption_key_epoch=1,
    )
    options = dict(config=config, signature_verifier=verifier, revocation_source=revocations,
                   ledger=ledger, clock=lambda: env.time,
                   monotonic_consumer=consumer, consumption_verifier=verifier)
    authority = module.AuthenticatedMaintenanceAuthorizationV1(**options)
    binding = env.m.AuthorizationBindingV1(
        scope=env.m.OFFLINE_MAINTENANCE_SCOPE, storage_root_binding_sha256=config.pinned_storage_root_sha256,
        nonce="synthetic-nonce", deadline=110.0,
    )
    def sign(binding, epoch=1):
        digest = module.maintenance_authorization_payload_sha256(binding, epoch)
        return {"payload_sha256": digest, "signature_sha256": hmac.new(key, digest.encode("ascii"), hashlib.sha256).hexdigest()}
    return SimpleNamespace(env=env, m=module, config=config, options=options, authority=authority,
                           ledger=ledger, revocations=revocations, binding=binding, sign=sign,
                           request=sign(binding), consumer=consumer, new_consumer=Consumer,
                           consumed=consumed, receipts=receipts, sign_receipt=sign_receipt)


def test_signed_authority_composes_with_complete_maintenance_chain(signed):
    e = signed.env
    result = e.build(consume_authorization=signed.authority).run_offline(signed.request)
    assert result["ok"] is True
    assert e.calls == ["bootstrap", "recovery", "postflight"]
    assert result["production_ready"] is False
    assert result["runtime_activation_allowed"] is False


def test_reconstructed_verifier_and_ledger_reject_replay(signed):
    assert signed.authority(signed.request, signed.binding) is True
    ledger = signed.m.SQLiteMaintenanceAuthorizationLedgerV1(signed.ledger._database, enabled=True)
    rebuilt = signed.m.AuthenticatedMaintenanceAuthorizationV1(**(signed.options | {"ledger": ledger}))
    assert rebuilt(signed.request, signed.binding) is False


def test_replacing_ledger_with_empty_database_cannot_reset_replay(signed):
    assert signed.authority(signed.request, signed.binding) is True
    ledger = signed.m.SQLiteMaintenanceAuthorizationLedgerV1(signed.env.root / "replacement.sqlite", enabled=True)
    ledger.provision()
    rebuilt = signed.m.AuthenticatedMaintenanceAuthorizationV1(**(signed.options | {"ledger": ledger}))
    assert rebuilt(signed.request, signed.binding) is False


def test_resigning_nonce_with_a_new_deadline_does_not_bypass_replay(signed):
    assert signed.authority(signed.request, signed.binding) is True
    changed = replace(signed.binding, deadline=120.0)
    assert signed.authority(signed.sign(changed), changed) is False


def test_restoring_old_ledger_at_same_path_must_not_reauthorize(signed):
    backup = signed.env.root / "synthetic-before-consumption.sqlite"
    with closing(sqlite3.connect(signed.ledger._database)) as source:
        with closing(sqlite3.connect(backup)) as target:
            source.backup(target)
    assert signed.authority(signed.request, signed.binding) is True
    # Restore only this test's temporary ledger, after all handles are closed.
    with closing(sqlite3.connect(backup)) as source:
        with closing(sqlite3.connect(signed.ledger._database)) as target:
            source.backup(target)
    ledger = signed.m.SQLiteMaintenanceAuthorizationLedgerV1(signed.ledger._database, enabled=True)
    assert ledger.storage_binding_sha256() == signed.config.pinned_ledger_storage_sha256
    rebuilt = signed.m.AuthenticatedMaintenanceAuthorizationV1(**(signed.options | {
        "ledger": ledger, "monotonic_consumer": signed.new_consumer(),
    }))
    assert rebuilt(signed.request, signed.binding) is False


def test_rotated_epoch_preserves_consumed_nonce_history(signed):
    assert signed.authority(signed.request, signed.binding) is True
    rotated = signed.m.AuthenticatedMaintenanceAuthorizationV1(**(signed.options | {
        "config": replace(signed.config, key_epoch=2),
    }))
    assert rotated(signed.sign(signed.binding, epoch=2), signed.binding) is False
    fresh = replace(signed.binding, nonce="synthetic-nonce-after-rotation")
    assert rotated(signed.sign(fresh, epoch=2), fresh) is True


@pytest.mark.parametrize("field,value", [
    ("scope", "PRODUCTION"), ("storage_root_binding_sha256", "b" * 64),
    ("nonce", "different"), ("deadline", 120.0), ("writer_count", 18),
    ("maintenance_only", False), ("writer_count", True),
])
def test_changed_binding_is_not_authorized(signed, field, value):
    assert signed.authority(signed.request, replace(signed.binding, **{field: value})) is False
    assert signed.env.calls == []


@pytest.mark.parametrize("change", ["signature", "hash_only", "revoked", "wrong_key", "wrong_epoch", "expired", "missing_verifier"])
def test_authentication_failures_do_not_consume_valid_request(signed, change):
    request = dict(signed.request)
    options = dict(signed.options)
    if change == "signature":
        request["signature_sha256"] = "a" * 64
    elif change == "hash_only":
        request.pop("signature_sha256")
    elif change == "revoked":
        signed.revocations.revoked = True
    elif change == "wrong_key":
        options["config"] = replace(signed.config, pinned_key_id_sha256="b" * 64)
    elif change == "wrong_epoch":
        options["config"] = replace(signed.config, key_epoch=2)
    elif change == "expired":
        signed.env.time = 110.0
    else:
        options["signature_verifier"] = None
    authority = signed.m.AuthenticatedMaintenanceAuthorizationV1(**options)
    assert authority(request, signed.binding) is False
    signed.revocations.revoked = False
    signed.env.time = 100.0
    assert signed.authority(signed.request, signed.binding) is True


def test_default_off_does_not_inspect_dependencies_or_request(signed):
    def bomb(*_):
        pytest.fail("dormant authorization performed I/O")
    authority = signed.m.AuthenticatedMaintenanceAuthorizationV1(clock=bomb)
    assert authority(object(), object()) is False
    assert signed.m.SQLiteMaintenanceAuthorizationLedgerV1().consume_once(claim_sha256="a" * 64, payload_sha256="b" * 64) is False


def test_unprovisioned_ledger_cannot_be_created_during_authorization(signed):
    database = signed.env.root / "must-not-exist.sqlite"
    ledger = signed.m.SQLiteMaintenanceAuthorizationLedgerV1(database, enabled=True)
    authority = signed.m.AuthenticatedMaintenanceAuthorizationV1(**(signed.options | {
        "ledger": ledger,
        "config": replace(signed.config, pinned_ledger_storage_sha256=ledger.storage_binding_sha256()),
    }))
    assert authority(signed.request, signed.binding) is False
    assert not database.exists()


def test_two_authorities_have_only_one_durable_winner(signed):
    results = []
    barrier = threading.Barrier(2)
    def consume():
        barrier.wait(timeout=3)
        results.append(signed.authority(signed.request, signed.binding))
    workers = [threading.Thread(target=consume) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(4)
        assert not worker.is_alive()
    assert sorted(results) == [False, True]


def test_invalid_ledger_schema_fails_closed(signed):
    database = signed.env.root / "bad-schema.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE c3_maintenance_claims (claim_sha256 TEXT, payload_sha256 TEXT)")
    ledger = signed.m.SQLiteMaintenanceAuthorizationLedgerV1(database, enabled=True)
    authority = signed.m.AuthenticatedMaintenanceAuthorizationV1(**(signed.options | {
        "ledger": ledger,
        "config": replace(signed.config, pinned_ledger_storage_sha256=ledger.storage_binding_sha256()),
    }))
    assert authority(signed.request, signed.binding) is False


def test_trigger_cannot_turn_duplicate_insert_into_success(signed):
    with sqlite3.connect(signed.ledger._database) as db:
        db.execute("CREATE TRIGGER ignore_claim BEFORE INSERT ON c3_maintenance_claims BEGIN SELECT RAISE(IGNORE); END")
    assert signed.authority(signed.request, signed.binding) is False


@pytest.mark.parametrize("failure", ["deadline", "revocation", "exception"])
def test_change_during_durable_consumption_denies_and_burns_request(signed, monkeypatch, failure):
    original = signed.ledger.consume_once
    def consume(**kwargs):
        assert original(**kwargs) is True
        if failure == "deadline":
            signed.env.time = signed.binding.deadline
        elif failure == "revocation":
            signed.revocations.revoked = True
        else:
            raise RuntimeError("private synthetic persistence detail")
        return True
    monkeypatch.setattr(signed.ledger, "consume_once", consume)
    assert signed.authority(signed.request, signed.binding) is False
    monkeypatch.setattr(signed.ledger, "consume_once", original)
    signed.env.time = 100.0
    signed.revocations.revoked = False
    assert signed.authority(signed.request, signed.binding) is False


def test_revocation_during_signature_verification_prevents_claim(signed, monkeypatch):
    def verify(**_):
        signed.revocations.revoked = True
        return True
    verifier = signed.options["signature_verifier"]
    original = verifier.verify_root_authority_signature_v2
    monkeypatch.setattr(verifier, "verify_root_authority_signature_v2", verify)
    assert signed.authority(signed.request, signed.binding) is False
    monkeypatch.setattr(verifier, "verify_root_authority_signature_v2", original)
    signed.revocations.revoked = False
    assert signed.authority(signed.request, signed.binding) is True


@lru_cache(maxsize=1)
def main_tree():
    return ast.parse((Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8-sig"))


def isolated_startup_prefix():
    tree = main_tree()
    binding = copy.deepcopy(next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_bind_c3_startup_maintenance_v1"))
    startup = copy.deepcopy(next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "start_central_runtime_once"))
    lock_index = next(i for i, n in enumerate(startup.body) if isinstance(n, ast.With))
    # Execute only real admission/flag code; replace all operational startup with
    # one harmless marker. No server, bot or worker code is compiled or imported.
    startup.body = startup.body[:lock_index + 1] + ast.parse("events.append('admitted')").body
    extracted = ast.fix_missing_locations(ast.Module(body=[binding, startup], type_ignores=[]))
    namespace = dict(CENTRAL_RUNTIME_STARTED=False, CENTRAL_RUNTIME_LOCK=threading.Lock(),
                     C3_MAINTENANCE_STARTUP_BINDING_V1=None, events=[], print=lambda *_: None)
    exec(compile(extracted, "<synthetic-startup-prefix>", "exec"), namespace)
    return namespace


def test_unbound_startup_preserves_existing_once_only_behavior(signed):
    ns = isolated_startup_prefix()
    ns["start_central_runtime_once"]()
    ns["start_central_runtime_once"]()
    assert ns["CENTRAL_RUNTIME_STARTED"] is True and ns["events"] == ["admitted"]


def test_binding_blocks_startup_before_and_after_successful_offline_completion(signed):
    ns = isolated_startup_prefix()
    composition = signed.env.build(consume_authorization=signed.authority)
    ns["_bind_c3_startup_maintenance_v1"](composition)
    assert ns["C3_MAINTENANCE_STARTUP_BINDING_V1"] is composition
    for complete in (False, True):
        if complete:
            assert composition.run_offline(signed.request)["ok"] is True
        with pytest.raises(RuntimeError, match="MAINTENANCE_BOUND_RUNTIME_START_FORBIDDEN"):
            ns["start_central_runtime_once"]()
        assert ns["CENTRAL_RUNTIME_STARTED"] is False and ns["events"] == []


@pytest.mark.skipif(sys.platform != "linux", reason="requires isolated Linux with real directory fsync")
def test_linux_signed_composition_and_startup_barrier_with_real_directory_fsync(signed):
    e = signed.env
    e.leases = e.s.DurableJsonMaintenanceLeaseStoreV1(e.root, enabled=True)
    composition = e.build(consume_authorization=signed.authority, lease_store=e.leases)
    ns = isolated_startup_prefix()
    ns["_bind_c3_startup_maintenance_v1"](composition)
    with pytest.raises(RuntimeError, match="MAINTENANCE_BOUND_RUNTIME_START_FORBIDDEN"):
        ns["start_central_runtime_once"]()
    result = composition.run_offline(signed.request)
    assert result["ok"] is True
    assert e.calls == ["bootstrap", "recovery", "postflight"]
    assert e.leases.read(e.c.canonical_runtime_lock_namespace_v1())["state"] == "RELEASED"
    assert result["production_ready"] is False and result["live_allowed"] is False
    for entry in e.c.canonical_runtime_writer_inventory_v1():
        with pytest.raises(e.c.WriterRuntimeCoordinationBlocked, match="MAINTENANCE_ONLY_WRITERS_FORBIDDEN"):
            with composition._coordinator.mutation(entry["writer_id"]):
                pytest.fail("writer admitted")
    with pytest.raises(RuntimeError, match="MAINTENANCE_BOUND_RUNTIME_START_FORBIDDEN"):
        ns["start_central_runtime_once"]()
    assert ns["events"] == [] and e.flushes == []


def test_binding_after_start_or_duplicate_binding_is_rejected(signed):
    for already_started in (False, True):
        ns = isolated_startup_prefix()
        composition = signed.env.build(consume_authorization=signed.authority)
        if already_started:
            ns["start_central_runtime_once"]()
        else:
            ns["_bind_c3_startup_maintenance_v1"](composition)
        with pytest.raises(RuntimeError, match="BINDING_UNAVAILABLE"):
            ns["_bind_c3_startup_maintenance_v1"](composition)


def test_plain_boolean_authenticator_cannot_be_bound_to_startup(signed):
    ns = isolated_startup_prefix()
    with pytest.raises(RuntimeError, match="BINDING_INVALID"):
        ns["_bind_c3_startup_maintenance_v1"](signed.env.build())
    assert ns["C3_MAINTENANCE_STARTUP_BINDING_V1"] is None


def test_binding_and_startup_race_cannot_both_succeed(signed):
    ns = isolated_startup_prefix()
    composition = signed.env.build(consume_authorization=signed.authority)
    barrier = threading.Barrier(2)
    outcomes = []
    def run(name, *args):
        barrier.wait(timeout=3)
        try:
            ns[name](*args)
            outcomes.append(name)
        except RuntimeError:
            pass
    workers = [threading.Thread(target=run, args=("_bind_c3_startup_maintenance_v1", composition)),
               threading.Thread(target=run, args=("start_central_runtime_once",))]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(4)
        assert not worker.is_alive()
    assert len(outcomes) == 1
    assert (ns["C3_MAINTENANCE_STARTUP_BINDING_V1"] is composition) is (not ns["CENTRAL_RUNTIME_STARTED"])


def test_no_automatic_binding_and_no_authentication_io_in_main(signed):
    tree = main_tree()
    initial = next(n for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "C3_MAINTENANCE_STARTUP_BINDING_V1" for t in n.targets))
    assert isinstance(initial.value, ast.Constant) and initial.value.value is None
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id == "_bind_c3_startup_maintenance_v1" for n in ast.walk(tree))
