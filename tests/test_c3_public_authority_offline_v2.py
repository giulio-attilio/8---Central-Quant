"""Public signatures, fresh revocation head and independent synthetic witness."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
import sqlite3

import pytest

from helpers.c3_public_authority_fixture import public_env
from helpers.c3_postgres_fixture import no_external_access, pg, NAMESPACE, INSTANCE
from test_trade_registry_c3_maintenance_activation_offline_v1 import env as maintenance_env
from test_trade_registry_c3_maintenance_activation_offline_v1 import supplied_coordinator
from test_trade_registry_c3_maintenance_activation_offline_v1 import recovery_values, recovery_composition_options


def backup(src, dst):
    with closing(sqlite3.connect(src)) as a, closing(sqlite3.connect(dst)) as b:
        a.backup(b)


def test_all_public_components_default_off_without_io(no_external_access):
    import trade_registry_c3_public_authority_offline_v2 as m
    def bomb(*args, **kwargs):
        pytest.fail("default-off touched dependency")
    assert m.Ed25519VerifierOfflineV2().verify(object(), purpose="request", payload_sha256="a" * 64) is False
    assert m.AnchoredRevocationsOfflineV2(clock=bomb, policy_reader=bomb).current(10) is None
    assert m.PublicPostgresConsumerOfflineV2(clock=bomb, signer=bomb).consume_once(
        namespace=None, claim_sha256=None, payload_sha256=None, challenge=None, deadline=None) is None
    assert m.PublicMaintenanceAuthorizationOfflineV2(clock=bomb)(object(), object()) is False


def test_public_chain_authorizes_once(public_env):
    e = public_env
    assert e.auth(e.request, e.binding) is True
    assert e.build()(e.request, e.binding) is False
    assert len(e.anchor.claims) == len(e.rows) == 1
    assert e.verifiers["request"].__dict__.keys() == {"enabled", "scope", "_public", "key_epoch"}
    assert e.request.signature_hex not in repr(e.request)
    assert e.root_binding not in repr(e.auth)


def direct_consumption_request(e):
    return dict(namespace=e.guard.namespace,
        claim_sha256=e.m._digest({"scope": e.binding.scope,
            "root": e.binding.storage_root_binding_sha256, "nonce": e.binding.nonce}),
        payload_sha256=e.request.payload_sha256, challenge="a" * 64, deadline=105.0,
        request=e.request, binding=e.binding)


def time_window_options():
    import trade_registry_c3_public_authority_offline_v2 as m
    return m, dict(enabled=True, scope=m.SCOPE, not_before_epoch_ms=1_000_000,
        expires_epoch_ms=1_010_000, now_lower_epoch_ms=1_004_000,
        now_upper_epoch_ms=1_004_050, local_remaining_ms=5_000,
        max_interval_width_ms=100)


@pytest.mark.parametrize("changes,expected", [
    ({}, 5_000), ({"local_remaining_ms": 17}, 17),
    ({"expires_epoch_ms": 1_004_100}, 50),
    ({"now_upper_epoch_ms": 1_009_999, "now_lower_epoch_ms": 1_009_949}, 1),
    ({"now_lower_epoch_ms": 1_000_000, "now_upper_epoch_ms": 1_000_000}, 5_000),
])
def test_time_window_uses_conservative_expiry_and_local_budget(changes, expected):
    m, options = time_window_options()
    assert m.remaining_epoch_window_ms_offline_v2(**(options | changes)) == expected


@pytest.mark.parametrize("changes", [
    {"enabled": False}, {"enabled": 1}, {"scope": "PRODUCTION"},
    {"not_before_epoch_ms": True}, {"expires_epoch_ms": 1_010_000.0},
    {"now_lower_epoch_ms": None}, {"now_upper_epoch_ms": float("nan")},
    {"local_remaining_ms": float("inf")}, {"max_interval_width_ms": None},
    {"now_lower_epoch_ms": -1}, {"expires_epoch_ms": 2**53},
    {"not_before_epoch_ms": 1_010_000}, {"expires_epoch_ms": 1_300_001},
    {"now_lower_epoch_ms": 999_999, "now_upper_epoch_ms": 1_000_001},
    {"now_lower_epoch_ms": 1_009_999, "now_upper_epoch_ms": 1_010_000},
    {"now_lower_epoch_ms": 1_004_051}, {"max_interval_width_ms": 49},
    {"local_remaining_ms": 0},
])
def test_time_window_invalid_or_uncertain_validity_has_no_budget(changes):
    m, options = time_window_options()
    assert m.remaining_epoch_window_ms_offline_v2(**(options | changes)) is None


def test_time_window_recheck_never_renews_last_admitted_budget():
    m, options = time_window_options()
    options["expires_epoch_ms"] = 1_004_125
    first = m.remaining_epoch_window_ms_offline_v2(**options)
    assert first == 75
    # Source uncertainty/clock changes cannot restore the previous local budget.
    # The caller measures remaining against its last admitted monotonic deadline.
    for elapsed in (0, 1, 50, 74):
        remaining = first - elapsed
        shifted = options | dict(now_lower_epoch_ms=1_003_000,
            now_upper_epoch_ms=1_003_050, local_remaining_ms=remaining)
        assert m.remaining_epoch_window_ms_offline_v2(**shifted) == remaining
    assert m.remaining_epoch_window_ms_offline_v2(**(options | {"local_remaining_ms": 0})) is None


def test_time_window_bounds_hold_for_synthetic_interval_grid():
    m, options = time_window_options()
    # Independent inequalities, not a second copy of the min implementation.
    accepted = 0
    for upper in range(1_000_000, 1_010_001, 137):
        for width in (0, 1, 50, 100, 101):
            for remaining in (0, 1, 499, 5_000, 9_000):
                lower = upper - width
                result = m.remaining_epoch_window_ms_offline_v2(**(options | dict(
                    now_lower_epoch_ms=lower, now_upper_epoch_ms=upper,
                    local_remaining_ms=remaining)))
                if result is None:
                    assert lower < options["not_before_epoch_ms"] or upper >= options["expires_epoch_ms"] or width > 100 or remaining == 0
                else:
                    accepted += 1
                    assert type(result) is int and 0 < result <= 5_000
                    assert result <= remaining
                    assert upper + result <= options["expires_epoch_ms"]
    assert accepted > 1_000


@pytest.mark.parametrize("change", ["deadline", "key_material", "both"])
def test_replay_reissue_preserves_claim_after_expiry_or_real_key_replacement(public_env, change):
    """Synthetic keys only; changing signed content must not reset replay identity."""
    e = public_env
    assert e.auth(e.request, e.binding) is True
    original_claims, original_rows = set(e.anchor.claims), dict(e.rows)
    binding = e.binding
    if change in {"deadline", "both"}:
        e.time = e.binding.deadline + 1
        binding = replace(binding, deadline=e.time + 10)
    if change in {"key_material", "both"}:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key = Ed25519PrivateKey.from_private_bytes(
            e.m.hashlib.sha256(b"PUBLIC-SYNTHETIC-C3-REPLACEMENT-REQUEST").digest())
        verifier = e.m.Ed25519VerifierOfflineV2(enabled=True, scope=e.m.SCOPE,
            public_key_bytes=key.public_key().public_bytes_raw(), key_epoch=2)
        assert verifier.key_id != e.verifiers["request"].key_id
        e.verifiers["request"] = verifier
        def sign(*, purpose, payload_sha256):
            message = e.m.signing_message_v2(purpose, verifier.key_id, verifier.key_epoch, payload_sha256)
            return e.m.SignatureV2(purpose, verifier.key_id, verifier.key_epoch,
                payload_sha256, key.sign(message).hex())
        e.signers["request"] = sign
        e.guard_options["protected_key_ids"] = tuple(v.key_id for v in e.verifiers.values())
        e.guard = e.m.AnchoredRevocationsOfflineV2(**e.guard_options)
    request = e.make_request(binding)
    payload, claim = e.m._verified_request_context_v2(request, binding,
        verifier=e.verifiers["request"], namespace=NAMESPACE, root_binding=e.root_binding,
        now=e.time, deadline=e.time + 5)
    assert payload != e.request.payload_sha256
    assert original_claims == {(NAMESPACE, claim)}
    assert e.build()(request, binding) is False
    assert e.anchor.claims == original_claims and e.rows == original_rows
    # Positive control: the replacement configuration is valid, not merely broken.
    fresh = replace(binding, nonce="synthetic-distinct-operation")
    assert e.build()(e.make_request(fresh), fresh) is True
    assert len(e.anchor.claims) == len(e.rows) == 2
    assert original_claims <= e.anchor.claims
    assert all(e.rows[k] == v for k, v in original_rows.items())


def test_direct_consumer_requires_complete_request_and_consumes_only_once(public_env):
    e = public_env
    call = direct_consumption_request(e)
    receipt = e.auth.consumer.consume_once(**call)
    assert type(receipt) is e.m.PublicConsumptionReceiptV2
    assert len(e.anchor.claims) == len(e.rows) == 1
    assert e.build().consumer.consume_once(**call) is None


@pytest.mark.parametrize("fault", ["missing_request", "missing_binding", "signature", "purpose",
    "unsigned_nonce", "payload", "claim", "namespace", "signed_foreign_root",
    "signed_runtime_scope", "signed_writer_count", "signed_not_maintenance",
    "over_budget", "beyond_signed_deadline", "expired", "nan_deadline", "bool_deadline"])
def test_direct_consumer_rejects_unbound_request_before_any_port(public_env, monkeypatch, fault):
    e = public_env
    call = direct_consumption_request(e)
    if fault == "missing_request":
        del call["request"]
    elif fault == "missing_binding":
        del call["binding"]
    elif fault in {"signature", "purpose"}:
        call["request"] = replace(e.request, **({"signature_hex": "f" * 128}
            if fault == "signature" else {"purpose": "policy"}))
    elif fault == "unsigned_nonce":
        call["binding"] = replace(e.binding, nonce="different")
    elif fault in {"payload", "claim", "namespace"}:
        call[{"payload": "payload_sha256", "claim": "claim_sha256", "namespace": "namespace"}[fault]] = "f" * 64
    elif fault.startswith("signed_") or fault == "beyond_signed_deadline":
        changes = {"signed_foreign_root": {"storage_root_binding_sha256": "f" * 64},
            "signed_runtime_scope": {"scope": "PRODUCTION"},
            "signed_writer_count": {"writer_count": 18},
            "signed_not_maintenance": {"maintenance_only": False},
            "beyond_signed_deadline": {"deadline": 104.0}}[fault]
        call["binding"] = replace(e.binding, **changes)
        call["request"] = e.make_request(call["binding"])
        call["payload_sha256"] = call["request"].payload_sha256
        call["claim_sha256"] = e.m._digest({"scope": call["binding"].scope,
            "root": call["binding"].storage_root_binding_sha256, "nonce": call["binding"].nonce})
    else:
        call["deadline"] = {"over_budget": 106.0, "expired": 100.0,
            "nan_deadline": float("nan"), "bool_deadline": True}[fault]
    calls = []
    def forbidden(*args, **kwargs):
        calls.append("unexpected port access")
        raise AssertionError("invalid request reached a persistence/policy/signing port")
    monkeypatch.setattr(e.guard, "current", forbidden)
    monkeypatch.setattr(e.store, "commit_digest_once", forbidden)
    monkeypatch.setattr(e.auth.consumer, "signer", forbidden)
    assert e.auth.consumer.consume_once(**call) is None
    assert calls == [] and not e.rows and not e.anchor.claims


@pytest.mark.parametrize("fault", ["missing_verifier", "other_role", "foreign_root", "different_instance"])
def test_consumer_request_pins_cannot_be_substituted(public_env, fault):
    e = public_env
    if fault == "missing_verifier":
        e.auth.consumer.request_verifier = None
    elif fault == "other_role":
        e.auth.consumer.request_verifier = e.verifiers["policy"]
    elif fault == "foreign_root":
        e.auth.consumer.root_binding = "f" * 64
    else:
        v = e.verifiers["request"]
        e.auth.consumer.request_verifier = e.m.Ed25519VerifierOfflineV2(
            enabled=True, scope=e.m.SCOPE, public_key_bytes=v._public, key_epoch=v.key_epoch)
    assert e.auth(e.request, e.binding) is False
    assert not e.rows and not e.anchor.claims


@pytest.mark.parametrize("other_origin", [0.0, 10000.0])
def test_direct_consumer_does_not_translate_foreign_clock_deadline(public_env, monkeypatch, other_origin):
    """No assumption that a remote monotonic timestamp is in our clock domain."""
    e = public_env
    call = direct_consumption_request(e)
    e.auth.consumer.clock = lambda: other_origin
    calls = []
    def forbidden(*args, **kwargs):
        calls.append("unexpected access")
        raise AssertionError("foreign-clock request reached policy or storage")
    monkeypatch.setattr(e.guard, "current", forbidden)
    monkeypatch.setattr(e.store, "commit_digest_once", forbidden)
    assert e.auth.consumer.consume_once(**call) is None
    assert calls == [] and not e.rows and not e.anchor.claims


@pytest.mark.parametrize("field,value", [("purpose", "policy"), ("key_id", "f" * 64),
    ("key_epoch", 2), ("key_epoch", True), ("payload_sha256", "f" * 64),
    ("signature_hex", "a" * 64), ("signature_hex", "a" * 128), ("signature_hex", "A" * 128)])
def test_signature_metadata_or_bytes_tamper_denied_before_consumption(public_env, field, value):
    e = public_env
    assert e.auth(replace(e.request, **{field: value}), e.binding) is False
    assert not e.rows and not e.anchor.claims


def test_public_bytes_cannot_be_used_as_signing_secret(public_env):
    e = public_env
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    fake = Ed25519PrivateKey.from_private_bytes(e.verifiers["request"]._public)
    s = e.request
    fake_sig = fake.sign(e.m.signing_message_v2(s.purpose, s.key_id, s.key_epoch, s.payload_sha256)).hex()
    assert e.auth(replace(s, signature_hex=fake_sig), e.binding) is False
    assert not e.anchor.claims


def test_no_legacy_hmac_or_boolean_fallback(public_env):
    e = public_env
    for request in (True, {}, {"payload_sha256": e.request.payload_sha256, "signature_sha256": "a" * 64}):
        assert e.auth(request, e.binding) is False
    assert not e.rows and not e.anchor.claims


@pytest.mark.parametrize("role", ["request", "consumer", "policy", "anchor"])
def test_revoked_role_blocks_all_consumption(public_env, role):
    e = public_env
    e.policy = e.anchor.policy = e.make_policy(2, [e.verifiers[role].key_id])
    assert e.auth(e.request, e.binding) is False and not e.anchor.claims


@pytest.mark.parametrize("field,value", [("generation", 0), ("generation", True),
    ("namespace", "f" * 64), ("issued_at", 101), ("expires_at", 100),
    ("expires_at", float("nan")), ("revoked_key_ids", ["a" * 64]),
    ("revoked_key_ids", ("a" * 64, "a" * 64))])
def test_invalid_policy_shape_time_or_signature_fails_closed(public_env, field, value):
    e = public_env
    e.policy = replace(e.policy, **{field: value})
    assert e.auth(e.request, e.binding) is False and not e.anchor.claims


def test_signed_policy_rollback_rejected_after_client_reconstruction(public_env):
    e = public_env
    old = e.policy
    e.anchor.policy = e.make_policy(2, [e.verifiers["request"].key_id])
    e.policy = old  # Older signature is valid but does not match the external head.
    fresh_guard = e.m.AnchoredRevocationsOfflineV2(**e.guard_options)
    assert e.build(guard=fresh_guard)(e.request, e.binding) is False
    assert not e.anchor.claims and not e.rows


def test_signed_same_generation_fork_rejected(public_env):
    e = public_env
    e.anchor.policy = e.make_policy(2, [e.verifiers["request"].key_id])
    e.policy = e.make_policy(2, [])
    assert e.auth(e.request, e.binding) is False and not e.anchor.claims


@pytest.mark.parametrize("failure", ["none", "exception", "cached", "tampered", "late"])
def test_external_head_failure_has_no_local_fallback(public_env, monkeypatch, failure):
    e = public_env
    original = e.anchor.read_head
    cached = e.guard.current(105)
    def broken(**kw):
        if failure == "none":
            return None
        if failure == "exception":
            raise TimeoutError("synthetic head unavailable")
        if failure == "cached":
            return cached
        result = original(**kw)
        if failure == "late":
            e.time = kw["deadline"]
            return result
        return replace(result, policy_generation=99)
    monkeypatch.setattr(e.anchor, "read_head", broken)
    assert e.auth(e.request, e.binding) is False and not e.anchor.claims


def test_policy_rotation_between_head_and_reservation_denied_atomically(public_env, monkeypatch):
    e = public_env
    original = e.anchor.reserve_once
    def rotated(**kw):
        e.anchor.policy = e.make_policy(2, [])
        return original(**kw)
    monkeypatch.setattr(e.anchor, "reserve_once", rotated)
    assert e.auth(e.request, e.binding) is False and not e.anchor.claims and not e.rows


@pytest.mark.parametrize("failure", ["lost_reservation", "bad_reservation", "store", "signer", "late_signer", "revoked_after_commit"])
def test_failures_after_reservation_burn_without_authorization(public_env, monkeypatch, failure):
    e = public_env
    if failure in ("lost_reservation", "bad_reservation"):
        original = e.anchor.reserve_once
        def broken(**kw):
            result = original(**kw)
            if failure == "lost_reservation":
                raise TimeoutError("synthetic lost reservation response")
            return replace(result, claim_sha256="f" * 64) if result else None
        monkeypatch.setattr(e.anchor, "reserve_once", broken)
    elif failure == "store":
        monkeypatch.setattr(e.store, "commit_digest_once", lambda **_: None)
    elif failure in ("signer", "late_signer"):
        def sign(**kw):
            if failure == "signer":
                raise RuntimeError("synthetic signer failure")
            result = e.signers["consumer"](**kw)
            e.time = 106
            return result
        e.auth.consumer.signer = sign
    else:
        original = e.store.commit_digest_once
        def revoke(**kw):
            result = original(**kw)
            e.policy = e.anchor.policy = e.make_policy(2, [e.verifiers["request"].key_id])
            return result
        monkeypatch.setattr(e.store, "commit_digest_once", revoke)
    assert e.auth(e.request, e.binding) is False and len(e.anchor.claims) == 1
    e.time = 100
    assert e.build()(e.request, e.binding) is False


def test_same_guard_instance_required(public_env):
    e = public_env
    e.auth.guard = e.m.AnchoredRevocationsOfflineV2(**e.guard_options)
    assert e.auth(e.request, e.binding) is False and not e.anchor.claims


@pytest.mark.parametrize("fault", ["backwards", "expired", "revoked"])
def test_final_policy_boundary_fails_closed(public_env, monkeypatch, fault):
    e = public_env
    consumed = []
    original_consume = e.ledger.consume_once
    original_current = e.guard.current
    def consume(**kw):
        result = original_consume(**kw)
        consumed.append(result)
        return result
    def current(deadline):
        if consumed:
            if fault == "backwards":
                e.time = 99.0  # Internally consistent guard clock, older than caller.
            elif fault == "expired":
                e.time = deadline
            else:
                e.policy = e.anchor.policy = e.make_policy(2, [e.verifiers["request"].key_id])
        return original_current(deadline)
    monkeypatch.setattr(e.ledger, "consume_once", consume)
    monkeypatch.setattr(e.guard, "current", current)
    assert e.auth(e.request, e.binding) is False
    assert consumed == [True] and len(e.anchor.claims) == len(e.rows) == 1


@pytest.mark.parametrize("field", ["reservation", "committed_digest", "signature"])
def test_tampered_consumption_receipt_is_not_authorization(public_env, monkeypatch, field):
    e = public_env
    original = e.auth.consumer.consume_once
    def consume(**kw):
        receipt = original(**kw)
        assert receipt is not None
        value = {"reservation": replace(receipt.reservation, challenge="f" * 64),
                 "committed_digest": "f" * 64, "signature": e.request}[field]
        return replace(receipt, **{field: value})
    monkeypatch.setattr(e.auth.consumer, "consume_once", consume)
    assert e.auth(e.request, e.binding) is False
    assert len(e.anchor.claims) == len(e.rows) == 1


def test_missing_crypto_library_has_no_fallback(public_env, monkeypatch):
    import builtins
    e = public_env
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.startswith("cryptography"):
            raise ImportError("synthetic unavailable cryptography")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    assert e.auth(e.request, e.binding) is False
    assert not e.anchor.claims and not e.rows


def test_captured_consumption_receipt_cannot_replay_after_local_restore(public_env, monkeypatch):
    e = public_env
    local = e.tmp / "synthetic-replay-backup.sqlite"
    backup(e.ledger._database, local)
    captured = []
    original = e.auth.consumer.consume_once
    def capture(**kw):
        receipt = original(**kw)
        captured.append(receipt)
        return receipt
    monkeypatch.setattr(e.auth.consumer, "consume_once", capture)
    assert e.auth(e.request, e.binding) is True
    backup(local, e.ledger._database)
    fresh = e.build()
    monkeypatch.setattr(fresh.consumer, "consume_once", lambda **kw: captured[0])
    assert fresh(e.request, e.binding) is False
    assert len(e.anchor.claims) == len(e.rows) == 1


def test_concurrent_full_chains_only_one_authorized(public_env):
    e = public_env
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: e.build()(e.request, e.binding), range(4)))
    assert sorted(results) == [False, False, False, True]
    assert len(e.rows) == len(e.anchor.claims) == 1


def test_restoring_both_local_stores_does_not_restore_external_claim(public_env):
    e = public_env
    path = e.tmp / "synthetic-local-backup.sqlite"
    backup(e.ledger._database, path)
    assert e.auth(e.request, e.binding) is True
    backup(path, e.ledger._database)
    e.rows.clear()  # Simulated PG rollback; retained external reference denies.
    assert e.build()(e.request, e.binding) is False and len(e.anchor.claims) == 1


def test_negative_control_restoring_the_external_reference_defeats_the_model(public_env):
    e = public_env
    path = e.tmp / "synthetic-local-backup.sqlite"
    backup(e.ledger._database, path)
    assert e.auth(e.request, e.binding) is True
    backup(path, e.ledger._database)
    e.rows.clear()
    e.anchor.claims.clear()  # Violates the independence assumption, intentionally.
    assert e.build()(e.request, e.binding) is True


def test_key_epoch_rotation_does_not_reset_claim_history(public_env):
    e = public_env
    assert e.auth(e.request, e.binding) is True
    e.verifiers["request"].key_epoch = 2
    new_request = e.make_request()
    assert new_request.key_epoch == 2 and new_request.payload_sha256 != e.request.payload_sha256
    assert e.build()(new_request, e.binding) is False
    assert len(e.anchor.claims) == 1


def real_store(e, pg, database="synthetic_c3"):
    return e.pg_module.PostgresConsumptionOfflineV1(config=e.pg_module.PostgresConsumptionConfigV1(
        enabled=True, scope=e.pg_module.OFFLINE_SCOPE, namespace_sha256=NAMESPACE, instance_sha256=INSTANCE),
        connect=lambda **kw: pg.connect(database=database, **kw), clock=lambda: e.time)


def test_real_postgres_full_public_authorization_and_restore(public_env, pg):
    e = public_env
    snapshot = pg.backup()
    local = e.tmp / "synthetic-local-backup.sqlite"
    backup(e.ledger._database, local)
    assert e.build(store=real_store(e, pg))(e.request, e.binding) is True
    assert pg.count() == 1 and len(e.anchor.claims) == 1
    pg.restore(snapshot)
    backup(local, e.ledger._database)
    assert e.build(store=real_store(e, pg, "synthetic_restore"))(e.request, e.binding) is False
    with pg.connect(user="cq-c3-lab", database="synthetic_restore") as db:
        assert db.execute("SELECT count(*) FROM c3_authority.claims").fetchone() == (0,)


def test_real_postgres_public_composition_keeps_maintenance_offline(public_env, pg, maintenance_env):
    e = public_env
    physical = maintenance_env
    e.root_binding = physical.options["storage_root_binding_sha256"]
    e.binding = replace(e.binding, storage_root_binding_sha256=e.root_binding, nonce="synthetic-nonce")
    auth = e.build(store=real_store(e, pg))
    composition = physical.build(consume_authorization=auth)
    result = composition.run_offline(e.make_request())
    assert result["ok"] is True
    assert result["live_allowed"] is False and result["runtime_activation_allowed"] is False
    assert result["production_ready"] is False and result["runtime_integrated"] is False
    assert physical.calls == ["bootstrap", "recovery", "postflight"]
    assert all(permit is physical.permits[0] for permit in physical.permits)
    assert pg.count() == 1 and len(e.anchor.claims) == 1


@pytest.mark.parametrize("fault", ["none", "root", "backend", "signature", "revocation", "lost_receipt"])
def test_public_authority_with_exact_injected_coordinator(public_env, maintenance_env, monkeypatch, fault):
    """Unit composition: fake consumption store, temporary physical lease, no PG server."""
    e, physical = public_env, maintenance_env
    e.root_binding = physical.options["storage_root_binding_sha256"]
    e.binding = replace(e.binding, storage_root_binding_sha256=e.root_binding, nonce="synthetic-nonce")
    auth = e.build()
    coordinator = supplied_coordinator(physical)
    options = dict(maintenance_coordinator=coordinator, consume_authorization=auth)
    request = e.make_request()
    if fault == "root":
        options["storage_root_binding_sha256"] = "a" * 64
    elif fault == "backend":
        coordinator._lock_backend = physical.s.CrossPlatformInterprocessFileLockBackendV1(physical.root, enabled=True)
    elif fault == "signature":
        request = replace(request, signature_hex="a" * 128)
    elif fault == "revocation":
        e.policy = e.anchor.policy = e.make_policy(2, [e.verifiers["request"].key_id])
    elif fault == "lost_receipt":
        original = auth.consumer.consume_once
        def lost(**kwargs):
            assert original(**kwargs) is not None
            return None
        monkeypatch.setattr(auth.consumer, "consume_once", lost)
    composition = physical.build(**options)
    outcome = composition.run_offline(request)
    assert outcome["ok"] is (fault == "none"), outcome["status"]
    assert outcome["production_ready"] is outcome["runtime_integrated"] is outcome["live_allowed"] is False
    assert physical.calls == (["bootstrap", "recovery", "postflight"] if fault == "none" else [])
    consumed = fault in {"none", "lost_receipt"}
    assert len(e.anchor.claims) == len(e.rows) == int(consumed)
    if fault == "none":
        assert composition._coordinator is coordinator
        assert physical.lease()["state"] == "RELEASED"
        assert all(p is physical.permits[0] for p in physical.permits)
    else:
        assert physical.lease() is None
    if consumed:
        # A fresh wrapper and request cannot resurrect consumed authority.
        before = list(physical.calls)
        retry = physical.build(maintenance_coordinator=coordinator, consume_authorization=e.build())
        assert retry.run_offline(e.make_request())["status"] == "C3_MAINTENANCE_AUTHORIZATION_DENIED"
        assert physical.calls == before and len(e.anchor.claims) == len(e.rows) == 1


def test_default_off_public_composition_does_not_consume(public_env, maintenance_env):
    physical, e = maintenance_env, public_env
    composition = physical.build(maintenance_coordinator=supplied_coordinator(physical),
        consume_authorization=e.auth, config=physical.m.MaintenanceActivationConfigV1())
    assert composition.run_offline(e.request)["status"] == "C3_MAINTENANCE_DEFAULT_OFF"
    assert not e.anchor.claims and not e.rows
    assert physical.calls == [] and physical.lease() is None


@pytest.mark.parametrize("fault", [
    "none", "signature", "public_revocation", "root_revocation", "root_expired",
    "lease_lost", "deadline", "foreign_coordinator", "first_store_receipt", "registry_write",
])
def test_public_authorization_maintenance_and_recovery_one_chain(
    public_env, maintenance_env, recovery_values, monkeypatch, fault,
):
    e, physical, values = public_env, maintenance_env, recovery_values
    coordinator = values["maintenance_coordinator"]
    # Different clock domains: budget at 100.0; authenticated root epoch at 1500.
    # Share the budget clock/nonce ports with maintenance, not the root epoch clock.
    coordinator._clock = physical.options["clock"]
    coordinator._nonce_source = physical.options["nonce_source"]
    assert coordinator._clock() == 100.0 and values["boundary"]._clock() == 1500
    chain = recovery_composition_options(physical, values,
        foreign_coordinator=fault == "foreign_coordinator", synthetic_registry_write=fault == "registry_write")
    e.root_binding = chain.options["storage_root_binding_sha256"]
    e.binding = replace(e.binding, storage_root_binding_sha256=e.root_binding, nonce="synthetic-nonce")
    options = chain.options | {"consume_authorization": e.build()}
    request = e.make_request()
    if fault == "signature":
        request = replace(request, signature_hex="a" * 128)
    elif fault == "public_revocation":
        e.policy = e.anchor.policy = e.make_policy(2, [e.verifiers["request"].key_id])
    elif fault == "root_revocation":
        monkeypatch.setattr(values["revocation"], "root_authority_key_revoked_v2", lambda **_: True)
    elif fault == "root_expired":
        monkeypatch.setattr(values["boundary"], "_clock", lambda: values["attestation"]["expires_at_epoch"])
    elif fault in {"lease_lost", "deadline"}:
        original = options["bootstrap"]
        def bootstrap(permit, deadline):
            result = original(permit, deadline)
            if fault == "deadline":
                physical.time = e.time = deadline
            else:
                lease = values["lease_store"].read(chain.used.lock_namespace)
                values["lease_store"].write(chain.used.lock_namespace, lease | {"state": "RELEASED"})
            return result
        options["bootstrap"] = bootstrap
    elif fault == "first_store_receipt":
        original = values["transaction_port"].recover_store_v2
        def corrupt(**kwargs):
            return original(**kwargs) | {"receipt_sha256": "a" * 64}
        monkeypatch.setattr(values["transaction_port"], "recover_store_v2", corrupt)
    composition = physical.build(**options)
    result = composition.run_offline(request)
    denied_auth = fault in {"signature", "public_revocation"}
    expected_status = ("C3_OFFLINE_MAINTENANCE_COMPLETED" if fault == "none" else
        "C3_MAINTENANCE_AUTHORIZATION_DENIED" if denied_auth else
        "C3_MAINTENANCE_PERMIT_INVALID" if fault == "lease_lost" else
        "C3_MAINTENANCE_DEADLINE_EXCEEDED" if fault == "deadline" else
        "C3_MAINTENANCE_RECOVERY_UNVERIFIED")
    assert result["status"] == expected_status, (
        result["status"], [(r.get("status"), r.get("reason")) for r in chain.reports])
    assert result["ok"] is (fault == "none")
    assert result["production_ready"] is result["runtime_integrated"] is result["live_allowed"] is False
    assert result["runtime_activation_allowed"] is result["coordination_ready"] is False
    expected_phases = ([] if denied_auth else ["bootstrap"] if fault in {"lease_lost", "deadline"}
                       else ["bootstrap", "recovery", "postflight"] if fault == "none"
                       else ["bootstrap", "recovery"])
    assert chain.phases == expected_phases
    first_called = fault in {"none", "registry_write", "first_store_receipt"}
    both_called = fault in {"none", "registry_write"}
    assert values["transaction_port"].call_count == int(first_called)
    assert values["resolved_port"].call_count == int(both_called)
    assert values["prepared"].call_count == int(both_called)
    assert len(e.anchor.claims) == len(e.rows) == int(not denied_auth)
    lease = values["lease_store"].read(chain.used.lock_namespace)
    assert lease is None if denied_auth else lease["state"] == "RELEASED"
    if both_called:
        report = chain.reports[0]
        assert report["registry_write"] is (fault == "registry_write")
        assert report["startup_recovery_attestation_sha256"] == chain.seam.startup_recovery_attestation_sha256_v1(report)
        assert report["production_authority"] is report["production_ready"] is False
    if not denied_auth:
        assert composition._coordinator is chain.used
        before = (list(chain.phases), values["transaction_port"].call_count,
                  values["resolved_port"].call_count, values["prepared"].call_count)
        # Reconstruct both callers after failure/success; consumed request stays burned.
        # Expired budget remains forward-only and is not reset just to make retry pass.
        e.time = physical.time
        fresh_binding = replace(e.binding, deadline=physical.time + 10)
        retry = physical.build(**(options | {"consume_authorization": e.build()}))
        assert retry.run_offline(e.make_request(fresh_binding))["status"] == "C3_MAINTENANCE_AUTHORIZATION_DENIED"
        assert before == (chain.phases, values["transaction_port"].call_count,
                          values["resolved_port"].call_count, values["prepared"].call_count)
        assert len(e.anchor.claims) == len(e.rows) == 1
