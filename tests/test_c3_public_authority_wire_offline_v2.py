"""Synthetic wire-format characterization, NOT a KMS adapter or AWS validation.

Only public reproducible test seeds; no client, credentials or network.
Emission scenarios use only a dedicated temporary synthetic SQLite database.
Run through c3_dependency_assembly_lab.py run-public-wire-offline.
"""

import base64
from dataclasses import replace
import hashlib
import json
import sqlite3
import threading
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

import trade_registry_c3_public_authority_offline_v2 as m


@pytest.fixture
def wire():
    # Public test data, never an operational credential or AWS key.
    key = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"C3-PUBLIC-WIRE-TEST-ONLY").digest())
    raw = key.public_key().public_bytes_raw()
    der = key.public_key().public_bytes(serialization.Encoding.DER,
                                       serialization.PublicFormat.SubjectPublicKeyInfo)
    verifier = m.Ed25519VerifierOfflineV2(enabled=True, scope=m.SCOPE,
                                        public_key_bytes=raw, key_epoch=7)
    return key, raw, der, verifier


def expected_message(purpose, fingerprint):
    # Independent literal protocol oracle: do not reuse signing_message_v2/json.dumps.
    return ('{"algorithm":"Ed25519","key_epoch":7,"key_id":"' + fingerprint
            + '","payload_sha256":"' + 'a' * 64 + '","purpose":"' + purpose
            + '","version":"C3_PUBLIC_AUTHORITY_SYNTHETIC_ONLY_V2"}').encode("ascii")


@pytest.mark.parametrize("purpose", ["request", "policy", "anchor_head", "anchor_reserve", "consumption"])
def test_spki_to_raw_and_full_envelope_signature(wire, purpose):
    key, raw, der, verifier = wire
    # HTTP/CLI representation is Base64(DER); SDK representation is DER bytes.
    transport = base64.b64encode(der).decode("ascii")
    decoded = serialization.load_der_public_key(base64.b64decode(transport, validate=True))
    assert isinstance(decoded, Ed25519PublicKey)
    assert decoded.public_bytes_raw() == raw and len(raw) == 32
    assert decoded.public_bytes(serialization.Encoding.DER,
                                serialization.PublicFormat.SubjectPublicKeyInfo) == der
    assert verifier.key_id == hashlib.sha256(raw).hexdigest()
    assert verifier.key_id != hashlib.sha256(der).hexdigest()
    message = expected_message(purpose, verifier.key_id)
    assert message == m.signing_message_v2(purpose, verifier.key_id, 7, "a" * 64)
    assert len(message) < 4096
    signature = m.SignatureV2(purpose, verifier.key_id, 7, "a" * 64, key.sign(message).hex())
    assert verifier.verify(signature, purpose=purpose, payload_sha256="a" * 64) is True
    assert signature.signature_hex not in repr(signature)
    assert m.Ed25519VerifierOfflineV2(public_key_bytes=raw).verify(
        signature, purpose=purpose, payload_sha256="a" * 64) is False


@pytest.mark.parametrize("variant", ["payload_only", "sha256_envelope", "sha512_envelope", "wrong_version", "whitespace"])
def test_other_signed_message_is_not_the_c3_envelope(wire, variant):
    key, raw, der, verifier = wire
    message = expected_message("request", verifier.key_id)
    other = {
        "payload_only": bytes.fromhex("a" * 64),
        "sha256_envelope": hashlib.sha256(message).digest(),
        "sha512_envelope": hashlib.sha512(message).digest(),
        "wrong_version": message.replace(b"SYNTHETIC_ONLY_V2", b"PRODUCTION_ONLY_V2"),
        "whitespace": message + b"\n",
    }[variant]
    # Ed25519 over a caller-prehashed message is NOT an Ed25519ph implementation.
    # This negative control tests accidental message substitution, not KMS PH mode.
    signature = m.SignatureV2("request", verifier.key_id, 7, "a" * 64, key.sign(other).hex())
    assert verifier.verify(signature, purpose="request", payload_sha256="a" * 64) is False


@pytest.mark.parametrize("encoding", ["der", "base64_der", "short_raw", "foreign_raw"])
def test_non_pinned_public_key_representation_cannot_verify(wire, encoding):
    key, raw, der, verifier = wire
    signature = m.SignatureV2("request", verifier.key_id, 7, "a" * 64,
                              key.sign(expected_message("request", verifier.key_id)).hex())
    supplied = {"der": der, "base64_der": base64.b64encode(der),
                "short_raw": raw[:-1], "foreign_raw": bytes(reversed(raw))}[encoding]
    other = m.Ed25519VerifierOfflineV2(enabled=True, scope=m.SCOPE,
                                     public_key_bytes=supplied, key_epoch=7)
    assert other.verify(signature, purpose="request", payload_sha256="a" * 64) is False


def test_signed_anchor_head_cannot_be_relabelled_as_reservation(wire):
    key, raw, der, verifier = wire
    signature = m.SignatureV2("anchor_head", verifier.key_id, 7, "a" * 64,
                              key.sign(expected_message("anchor_head", verifier.key_id)).hex())
    assert verifier.verify(replace(signature, purpose="anchor_reserve"),
                           purpose="anchor_reserve", payload_sha256="a" * 64) is False


@pytest.fixture
def epoch_request(wire):
    key, raw, _, verifier = wire
    request = m.EpochRequestOfflineV3("a" * 64, "b" * 64, "synthetic-epoch-nonce",
                                    1_000_000, 1_010_000, verifier.key_id, 7)
    # Literal oracle, independent of the implementation's serializer/field discovery.
    message = ('{"algorithm":"Ed25519","expires_epoch_ms":1010000,"key_epoch":7,"key_id":"'
        + verifier.key_id + '","maintenance_only":true,"namespace":"' + 'a' * 64
        + '","nonce":"synthetic-epoch-nonce","not_before_epoch_ms":1000000,"purpose":"request",'
        '"scope":"C3_COORDINATED_MAINTENANCE_OFFLINE_V1","storage_root_binding_sha256":"'
        + 'b' * 64 + '","version":"C3_PUBLIC_EPOCH_REQUEST_SYNTHETIC_ONLY_V3","writer_count":19}').encode("ascii")
    signed = replace(request, signature_hex=key.sign(message).hex())
    pins = dict(enabled=True, scope=m.EPOCH_REQUEST_SCOPE, public_key_bytes=raw,
                expected_key_epoch=7, expected_namespace="a" * 64, expected_root="b" * 64)
    return signed, message, pins


def test_epoch_v3_literal_signature_and_replay_identity(epoch_request):
    request, message, pins = epoch_request
    assert m.epoch_request_signing_message_offline_v3(request, enabled=True, scope=m.EPOCH_REQUEST_SCOPE) == message
    assert m.epoch_request_signature_verified_offline_v3(request, **pins) is True
    # A cryptographic check is deliberately repeatable, unlike authority consumption.
    assert m.epoch_request_signature_verified_offline_v3(request, **pins) is True
    oracle = ('{"nonce":"synthetic-epoch-nonce","root":"' + 'b' * 64
              + '","scope":"C3_COORDINATED_MAINTENANCE_OFFLINE_V1"}').encode("ascii")
    claim = m.epoch_request_claim_offline_v3(request, enabled=True, scope=m.EPOCH_REQUEST_SCOPE)
    assert claim == hashlib.sha256(oracle).hexdigest()
    for changes in ({"expires_epoch_ms": 1_020_000}, {"key_id": "c" * 64, "key_epoch": 8}):
        other = replace(request, **changes)
        assert m.epoch_request_claim_offline_v3(other, enabled=True, scope=m.EPOCH_REQUEST_SCOPE) == claim
        assert m.epoch_request_signing_message_offline_v3(other, enabled=True, scope=m.EPOCH_REQUEST_SCOPE) != message
    assert request.nonce not in repr(request) and request.signature_hex not in repr(request)


@pytest.mark.parametrize("changes", [
    {"namespace": "c" * 64}, {"storage_root_binding_sha256": "c" * 64},
    {"nonce": "different"}, {"not_before_epoch_ms": 1_000_001}, {"expires_epoch_ms": 1_010_001},
    {"key_id": "c" * 64}, {"key_epoch": 8}, {"scope": "PRODUCTION"},
    {"writer_count": 18}, {"maintenance_only": False}, {"signature_hex": "a" * 128},
])
def test_epoch_v3_tamper_denied(epoch_request, changes):
    request, _, pins = epoch_request
    assert m.epoch_request_signature_verified_offline_v3(replace(request, **changes), **pins) is False


@pytest.mark.parametrize("changes", [
    {"nonce": ""}, {"nonce": "a" * 257}, {"nonce": "\ud800"},
    {"not_before_epoch_ms": True}, {"not_before_epoch_ms": -1},
    {"expires_epoch_ms": float("nan")}, {"expires_epoch_ms": 1_010_000.0},
    {"expires_epoch_ms": 2**53}, {"expires_epoch_ms": 1_000_000},
    {"expires_epoch_ms": 1_300_001}, {"key_epoch": True}, {"key_epoch": 0},
    {"writer_count": True}, {"maintenance_only": 1},
])
def test_epoch_v3_invalid_shape_has_no_message_or_claim(epoch_request, changes):
    request, _, pins = epoch_request
    request = replace(request, **changes)
    options = dict(enabled=True, scope=m.EPOCH_REQUEST_SCOPE)
    assert m.epoch_request_signing_message_offline_v3(request, **options) is None
    assert m.epoch_request_claim_offline_v3(request, **options) is None
    assert m.epoch_request_signature_verified_offline_v3(request, **pins) is False


@pytest.mark.parametrize("changes", [
    {"enabled": False}, {"enabled": 1}, {"scope": m.SCOPE},
    {"public_key_bytes": None}, {"public_key_bytes": b"x" * 32},
    {"expected_key_epoch": True}, {"expected_key_epoch": 8},
    {"expected_namespace": None}, {"expected_namespace": "c" * 64},
    {"expected_root": "c" * 64},
])
def test_epoch_v3_explicit_pins_required(epoch_request, changes):
    request, _, pins = epoch_request
    assert m.epoch_request_signature_verified_offline_v3(request, **(pins | changes)) is False


@pytest.mark.parametrize("variant", ["v2", "production", "purpose", "prehash", "newline"])
def test_epoch_v3_foreign_signed_domain_rejected(epoch_request, wire, variant):
    request, message, pins = epoch_request
    key = wire[0]
    other = {"v2": message.replace(m.EPOCH_REQUEST_SCOPE.encode(), m.SCOPE.encode()),
             "production": message.replace(b"SYNTHETIC_ONLY", b"PRODUCTION_ONLY"),
             "purpose": message.replace(b'"purpose":"request"', b'"purpose":"policy"'),
             "prehash": hashlib.sha256(message).digest(), "newline": message + b"\n"}[variant]
    assert m.epoch_request_signature_verified_offline_v3(
        replace(request, signature_hex=key.sign(other).hex()), **pins) is False


def test_epoch_v3_default_off_and_v2_type_separation(epoch_request, wire):
    request, _, pins = epoch_request
    assert m.epoch_request_signing_message_offline_v3(object()) is None
    assert m.epoch_request_claim_offline_v3(object()) is None
    assert m.epoch_request_signature_verified_offline_v3(object()) is False
    assert wire[3].verify(request, purpose="request", payload_sha256="a" * 64) is False
    legacy = m.SignatureV2("request", request.key_id, 7, "a" * 64, request.signature_hex)
    assert m.epoch_request_signature_verified_offline_v3(legacy, **pins) is False
    with pytest.raises(ValueError):
        m._verified_request_context_v2(request, request, verifier=wire[3],
            namespace=request.namespace, root_binding=request.storage_root_binding_sha256,
            now=100, deadline=105)


@pytest.mark.parametrize("signature", [None, "a" * 64, "A" * 128, True])
def test_epoch_v3_malformed_signature_rejected(epoch_request, signature):
    request, _, pins = epoch_request
    assert m.epoch_request_signature_verified_offline_v3(
        replace(request, signature_hex=signature), **pins) is False


def test_epoch_v3_missing_crypto_fails_closed(epoch_request, monkeypatch):
    import builtins
    request, _, pins = epoch_request
    original = builtins.__import__
    def no_crypto(name, *args, **kwargs):
        if name.startswith("cryptography"):
            raise ImportError("synthetic crypto unavailable")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", no_crypto)
    assert m.epoch_request_signature_verified_offline_v3(request, **pins) is False


def test_epoch_v3_max_unicode_nonce_fits_unsigned_message_bound(epoch_request, wire):
    request, _, pins = epoch_request
    # Each non-BMP scalar requires twelve ASCII bytes in ensure_ascii JSON.
    request = replace(request, nonce="\U0010ffff" * 256, key_epoch=2**53 - 1,
                      not_before_epoch_ms=2**53 - 2, expires_epoch_ms=2**53 - 1)
    message = m.epoch_request_signing_message_offline_v3(request, enabled=True, scope=m.EPOCH_REQUEST_SCOPE)
    assert type(message) is bytes and len(message) <= 4096
    assert message.count(b"\\udbff\\udfff") == 256
    signed = replace(request, signature_hex=wire[0].sign(message).hex())
    assert m.epoch_request_signature_verified_offline_v3(
        signed, **(pins | {"expected_key_epoch": 2**53 - 1})) is True


@pytest.fixture
def epoch_bundle(epoch_request, wire):
    request, _, _ = epoch_request
    keys = {"request": wire[0]}
    for role in ("policy", "anchor", "consumption"):
        keys[role] = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(
            ("PUBLIC-SYNTHETIC-EPOCH-" + role).encode()).digest())
    public = {role: k.public_key().public_bytes_raw() for role, k in keys.items()}
    ids = {role: hashlib.sha256(k).hexdigest() for role, k in public.items()}
    def message(s):
        return m.epoch_statement_signing_message_offline_v3(s, enabled=True, scope=m.EPOCH_STATEMENT_SCOPE)
    def digest(s):
        return hashlib.sha256(message(s)).hexdigest()
    def sign(s, *, message_override=None):
        role = ("policy" if type(s) is m.EpochPolicyOfflineV3 else
                "anchor" if type(s) is m.EpochAnchorOfflineV3 else "consumption")
        return replace(s, signature_hex=keys[role].sign(message(s) if message_override is None else message_override).hex())
    policy = sign(m.EpochPolicyOfflineV3(request.namespace, 3, 999_000, 1_020_000, (), ids["policy"], 7))
    payload = hashlib.sha256(m.epoch_request_signing_message_offline_v3(
        request, enabled=True, scope=m.EPOCH_REQUEST_SCOPE)).hexdigest()
    head = sign(m.EpochAnchorOfflineV3("anchor_head", request.namespace, "c" * 64,
        3, digest(policy), payload, "d" * 64, 1_001_000, 1_005_000, ids["anchor"], 7))
    reservation = sign(replace(head, purpose="anchor_reserve", challenge="e" * 64,
        not_before_epoch_ms=1_002_000, expires_epoch_ms=1_004_000,
        claim_sha256=m.epoch_request_claim_offline_v3(request, enabled=True, scope=m.EPOCH_REQUEST_SCOPE)))
    consumption = sign(m.EpochConsumptionOfflineV3(reservation, digest(reservation), ids["consumption"], 7))
    options = dict(enabled=True, scope=m.EPOCH_STATEMENT_SCOPE, request=request, policy=policy,
        head=head, reservation=reservation, consumption=consumption, public_keys=public,
        key_epochs={r: 7 for r in keys}, expected_namespace=request.namespace,
        expected_root=request.storage_root_binding_sha256, expected_instance="c" * 64,
        expected_head_challenge="d" * 64, expected_reservation_challenge="e" * 64)
    def pins(target):
        role = {"policy": "policy", "head": "anchor", "reservation": "anchor", "consumption": "consumption"}[target]
        return dict(enabled=True, scope=m.EPOCH_STATEMENT_SCOPE, public_key_bytes=public[role],
            expected_key_epoch=7, expected_namespace=request.namespace,
            expected_instance=None if target == "policy" else "c" * 64,
            expected_purpose={"head": "anchor_head", "reservation": "anchor_reserve"}.get(target, target))
    return options, sign, digest, pins


@pytest.mark.parametrize("target", ["policy", "head", "reservation", "consumption"])
def test_epoch_statements_v3_literal_messages(epoch_bundle, target):
    options, _, digest, pins = epoch_bundle
    s = options[target]
    # Independent literal encodings; do not call json.dumps or enumerate dataclass fields.
    if target == "policy":
        expected = ('{"algorithm":"Ed25519","expires_epoch_ms":1020000,"generation":3,'
            '"issued_at_epoch_ms":999000,"key_epoch":7,"key_id":"' + s.key_id
            + '","namespace":"' + 'a' * 64 + '","purpose":"policy","revoked_key_ids":[],')
    elif target in {"head", "reservation"}:
        claim = 'null' if target == "head" else '"' + s.claim_sha256 + '"'
        start, end = (1001000, 1005000) if target == "head" else (1002000, 1004000)
        expected = ('{"algorithm":"Ed25519","challenge":"' + s.challenge
            + '","claim_sha256":' + claim + ',"expires_epoch_ms":' + str(end)
            + ',"instance":"' + 'c' * 64 + '","key_epoch":7,"key_id":"' + s.key_id
            + '","namespace":"' + 'a' * 64 + '","not_before_epoch_ms":' + str(start)
            + ',"payload_sha256":"' + s.payload_sha256 + '","policy_generation":3,"policy_sha256":"'
            + s.policy_sha256 + '","purpose":"' + s.purpose + '",')
    else:
        expected = ('{"algorithm":"Ed25519","committed_digest":"' + s.committed_digest
            + '","key_epoch":7,"key_id":"' + s.key_id + '","purpose":"consumption",'
            '"reservation_sha256":"' + digest(s.reservation) + '",')
    expected = (expected + '"version":"C3_PUBLIC_EPOCH_STATEMENT_SYNTHETIC_ONLY_V3"}').encode("ascii")
    assert m.epoch_statement_signing_message_offline_v3(s, enabled=True, scope=m.EPOCH_STATEMENT_SCOPE) == expected
    assert m.epoch_statement_signature_verified_offline_v3(s, **pins(target)) is True
    assert s.key_id not in repr(s) and s.signature_hex not in repr(s)


@pytest.mark.parametrize("target,field,value", [
    ("policy", "namespace", "f" * 64), ("policy", "generation", 4),
    ("policy", "issued_at_epoch_ms", 999001), ("policy", "expires_epoch_ms", 1020001),
    ("policy", "revoked_key_ids", ("f" * 64,)), ("policy", "key_id", "f" * 64),
    ("policy", "key_epoch", 8), ("policy", "signature_hex", "f" * 128),
    ("head", "purpose", "anchor_reserve"), ("head", "namespace", "f" * 64),
    ("head", "instance", "f" * 64), ("head", "policy_generation", 4),
    ("head", "policy_sha256", "f" * 64), ("head", "payload_sha256", "f" * 64),
    ("head", "challenge", "f" * 64), ("head", "not_before_epoch_ms", 1001001),
    ("head", "expires_epoch_ms", 1005001), ("head", "key_id", "f" * 64),
    ("head", "key_epoch", 8), ("head", "claim_sha256", "f" * 64),
    ("head", "signature_hex", "f" * 128), ("reservation", "claim_sha256", "f" * 64),
    ("consumption", "committed_digest", "f" * 64), ("consumption", "key_id", "f" * 64),
    ("consumption", "key_epoch", 8), ("consumption", "signature_hex", "f" * 128),
])
def test_epoch_statements_v3_tamper_denied(epoch_bundle, target, field, value):
    options, _, _, pins = epoch_bundle
    other = replace(options[target], **{field: value})
    assert m.epoch_statement_signature_verified_offline_v3(other, **pins(target)) is False


@pytest.mark.parametrize("target,field,value", [
    ("policy", "generation", True), ("policy", "generation", 0),
    ("policy", "issued_at_epoch_ms", -1), ("policy", "expires_epoch_ms", float("nan")),
    ("policy", "expires_epoch_ms", 2**53), ("policy", "expires_epoch_ms", 1299001),
    ("policy", "revoked_key_ids", []), ("policy", "revoked_key_ids", ("f" * 64,) * 2),
    ("policy", "revoked_key_ids", tuple(f"{i:064x}" for i in range(129))),
    ("policy", "revoked_key_ids", ("f" * 64, "a" * 64)),
    ("head", "purpose", "consumption"), ("head", "policy_generation", False),
    ("head", "expires_epoch_ms", 1006001), ("head", "not_before_epoch_ms", 1001000.0),
    ("head", "expires_epoch_ms", 1001000), ("reservation", "claim_sha256", None),
    ("consumption", "reservation", None), ("consumption", "key_epoch", True),
])
def test_epoch_statements_v3_bad_shape_fails_closed(epoch_bundle, target, field, value):
    options, _, _, pins = epoch_bundle
    s = replace(options[target], **{field: value})
    assert m.epoch_statement_signing_message_offline_v3(s, enabled=True, scope=m.EPOCH_STATEMENT_SCOPE) is None
    assert m.epoch_statement_signature_verified_offline_v3(s, **pins(target)) is False


def test_epoch_statements_v3_chain_consistency_is_repeatable_not_authority(epoch_bundle):
    options, _, _, _ = epoch_bundle
    assert m.epoch_evidence_signatures_consistent_offline_v3(**options) is True
    assert m.epoch_evidence_signatures_consistent_offline_v3(**options) is True
    assert m.epoch_evidence_signatures_consistent_offline_v3() is False
    assert m.epoch_evidence_signatures_consistent_offline_v3(**(options | {"enabled": 1})) is False
    assert m.epoch_evidence_signatures_consistent_offline_v3(**(options | {"scope": m.SCOPE})) is False


@pytest.mark.parametrize("fault", ["head_payload", "reservation_payload", "generation", "policy_hash",
    "head_challenge", "reservation_challenge", "claim", "head_before_request", "reservation_before_head",
    "reservation_after_head", "policy_expires_before_head", "embedded_reservation", "revoked_request",
    "revoked_policy", "revoked_anchor", "revoked_consumption"])
def test_epoch_statements_v3_valid_signatures_with_wrong_links_denied(epoch_bundle, fault):
    options, sign, digest, pins = epoch_bundle
    changed = dict(options)
    if fault.startswith("revoked_") or fault == "policy_expires_before_head":
        changes = ({"expires_epoch_ms": 1004500} if fault == "policy_expires_before_head" else
            {"revoked_key_ids": (hashlib.sha256(options["public_keys"][fault.removeprefix("revoked_")]).hexdigest(),)})
        changed["policy"] = sign(replace(options["policy"], **changes))
        for target in ("head", "reservation"):
            changed[target] = sign(replace(changed[target], policy_sha256=digest(changed["policy"])))
    else:
        target, field, value = {
            "head_payload": ("head", "payload_sha256", "f" * 64),
            "reservation_payload": ("reservation", "payload_sha256", "f" * 64),
            "generation": ("reservation", "policy_generation", 4),
            "policy_hash": ("reservation", "policy_sha256", "f" * 64),
            "head_challenge": ("head", "challenge", "f" * 64),
            "reservation_challenge": ("reservation", "challenge", "f" * 64),
            "claim": ("reservation", "claim_sha256", "f" * 64),
            "head_before_request": ("head", "not_before_epoch_ms", 999999),
            "reservation_before_head": ("reservation", "not_before_epoch_ms", 1000000),
            "reservation_after_head": ("reservation", "expires_epoch_ms", 1005001),
            "embedded_reservation": ("reservation", "challenge", "f" * 64),
        }[fault]
        # Keep the widened head within the independent five-second format cap.
        if fault == "head_before_request":
            changed["head"] = replace(changed["head"], expires_epoch_ms=1004000)
        changed[target] = sign(replace(changed[target], **{field: value}))
        if fault == "embedded_reservation":
            changed["expected_reservation_challenge"] = "f" * 64
    if fault != "embedded_reservation":
        changed["consumption"] = sign(replace(changed["consumption"], reservation=changed["reservation"],
                                              committed_digest=digest(changed["reservation"])))
    # Failures must be due to links/revocation/containment, not invalid signatures.
    for target in ("policy", "head", "reservation", "consumption"):
        assert m.epoch_statement_signature_verified_offline_v3(changed[target], **pins(target)) is True
    assert m.epoch_evidence_signatures_consistent_offline_v3(**changed) is False


@pytest.mark.parametrize("field,value", [("expected_namespace", "f" * 64), ("expected_root", "f" * 64),
    ("expected_instance", "f" * 64), ("expected_head_challenge", None),
    ("expected_reservation_challenge", "f" * 64), ("key_epochs", {}), ("public_keys", {})])
def test_epoch_statements_v3_chain_requires_explicit_pins(epoch_bundle, field, value):
    options, _, _, _ = epoch_bundle
    assert m.epoch_evidence_signatures_consistent_offline_v3(**(options | {field: value})) is False


def test_epoch_statements_v3_role_key_separation_required(epoch_bundle):
    options, _, _, _ = epoch_bundle
    keys = options["public_keys"] | {"consumption": options["public_keys"]["anchor"]}
    assert m.epoch_evidence_signatures_consistent_offline_v3(**(options | {"public_keys": keys})) is False


@pytest.mark.parametrize("target", ["policy", "head", "reservation", "consumption"])
@pytest.mark.parametrize("variant", ["v2", "prehash", "purpose"])
def test_epoch_statements_v3_foreign_signed_envelope_rejected(epoch_bundle, target, variant):
    options, sign, _, pins = epoch_bundle
    s = options[target]
    message = m.epoch_statement_signing_message_offline_v3(s, enabled=True, scope=m.EPOCH_STATEMENT_SCOPE)
    other = {"v2": message.replace(m.EPOCH_STATEMENT_SCOPE.encode(), m.SCOPE.encode()),
             "prehash": hashlib.sha256(message).digest(),
             "purpose": message.replace(('"purpose":"' + pins(target)["expected_purpose"] + '"').encode(),
                                        b'"purpose":"request"')}[variant]
    assert m.epoch_statement_signature_verified_offline_v3(sign(s, message_override=other), **pins(target)) is False


@pytest.mark.parametrize("target", ["policy", "head", "reservation", "consumption"])
def test_epoch_statements_v3_default_off_and_wrong_purpose_or_version(epoch_bundle, wire, target):
    options, _, _, pins = epoch_bundle
    s = options[target]
    assert m.epoch_statement_signing_message_offline_v3(object()) is None
    assert m.epoch_statement_signature_verified_offline_v3(object()) is False
    assert m.epoch_statement_signature_verified_offline_v3(s, **(pins(target) | {"scope": m.SCOPE})) is False
    assert m.epoch_statement_signature_verified_offline_v3(s, **(pins(target) | {"expected_purpose": "request"})) is False
    assert wire[3].verify(s, purpose="policy", payload_sha256="a" * 64) is False
    with pytest.raises(ValueError):
        m.statement_digest_v2(s)


def test_epoch_statements_v3_max_policy_and_consumption_binding(epoch_bundle):
    options, sign, digest, pins = epoch_bundle
    policy = replace(options["policy"], revoked_key_ids=tuple(f"{i:064x}" for i in range(128)),
                     generation=2**53 - 1)
    message = m.epoch_statement_signing_message_offline_v3(policy, enabled=True, scope=m.EPOCH_STATEMENT_SCOPE)
    assert 8192 < len(message) <= 16384
    assert m.epoch_statement_signature_verified_offline_v3(sign(policy), **pins("policy")) is True
    bad = replace(options["consumption"], reservation=options["head"], committed_digest=digest(options["head"]))
    assert m.epoch_statement_signing_message_offline_v3(bad, enabled=True, scope=m.EPOCH_STATEMENT_SCOPE) is None


def codec_scope(target):
    return m.EPOCH_REQUEST_SCOPE if target == "request" else m.EPOCH_STATEMENT_SCOPE


def codec_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


@pytest.mark.parametrize("target", ["request", "policy", "head", "reservation", "consumption"])
def test_epoch_codec_v3_exact_roundtrip_and_signature_bytes(epoch_bundle, target):
    options, _, _, _ = epoch_bundle
    original = options[target]
    scope = codec_scope(target)
    unsigned = (m.epoch_request_signing_message_offline_v3 if target == "request" else
                m.epoch_statement_signing_message_offline_v3)(original, enabled=True, scope=scope)
    # Independent placement of the signature in the already tested canonical oracle.
    following = b',"storage_root_binding_sha256"' if target == "request" else b',"version"'
    expected = unsigned.replace(following, b',"signature_hex":"' + original.signature_hex.encode() + b'"' + following)
    wire = m.epoch_wire_encode_offline_v3(original, enabled=True, scope=scope)
    assert wire == expected and len(wire) == len(unsigned) + 147
    decoded = m.epoch_wire_decode_offline_v3(wire, enabled=True, scope=scope,
        reservation=options["reservation"] if target == "consumption" else None)
    assert type(decoded) is type(original) and decoded == original and decoded is not original
    assert decoded.signature_hex == original.signature_hex
    assert m.epoch_wire_encode_offline_v3(decoded, enabled=True, scope=scope) == wire
    if target == "consumption":
        assert decoded.reservation is options["reservation"]


def test_epoch_codec_v3_complete_chain_remains_consistent(epoch_bundle):
    options, _, _, _ = epoch_bundle
    decoded = {}
    for target in ("request", "policy", "head", "reservation", "consumption"):
        scope = codec_scope(target)
        wire = m.epoch_wire_encode_offline_v3(options[target], enabled=True, scope=scope)
        decoded[target] = m.epoch_wire_decode_offline_v3(wire, enabled=True, scope=scope,
            reservation=decoded.get("reservation") if target == "consumption" else None)
        assert decoded[target] is not None
    assert m.epoch_evidence_signatures_consistent_offline_v3(**(options | decoded)) is True


@pytest.mark.parametrize("variant", ["duplicate_equal", "duplicate_different", "duplicate_escaped",
    "whitespace", "key_order", "escaped_key", "float", "exponent", "nan", "infinity",
    "negative_zero", "huge_int", "utf8", "bom", "trailing_json", "unknown", "missing_default",
    "version", "algorithm", "purpose", "nested", "bool_integer", "null_integer", "integer_string",
    "surrogate", "nonce_oversize", "signature_missing", "signature_upper"])
def test_epoch_codec_v3_ambiguous_or_invalid_request_rejected(epoch_bundle, variant):
    options, _, _, _ = epoch_bundle
    wire = m.epoch_wire_encode_offline_v3(options["request"], enabled=True, scope=m.EPOCH_REQUEST_SCOPE)
    document = json.loads(wire)
    mutations = {
        "duplicate_equal": b'"key_epoch":7,"key_epoch":7',
        "duplicate_different": b'"key_epoch":8,"key_epoch":7',
        "duplicate_escaped": b'"key_epoch":7,"key_\\u0065poch":7',
        "float": b'"key_epoch":7.0', "exponent": b'"key_epoch":7e0',
        "nan": b'"key_epoch":NaN', "infinity": b'"key_epoch":Infinity',
        "negative_zero": b'"key_epoch":-0', "huge_int": b'"key_epoch":' + b'9' * 100,
    }
    if variant in mutations:
        wire = wire.replace(b'"key_epoch":7', mutations[variant])
    elif variant == "whitespace":
        wire += b"\n"
    elif variant == "key_order":
        wire = json.dumps(dict(reversed(list(document.items()))), separators=(",", ":")).encode()
    elif variant == "escaped_key":
        wire = wire.replace(b'"nonce"', b'"\\u006eonce"')
    elif variant == "utf8":
        wire = wire.replace(b"synthetic", b"\xff", 1)
    elif variant == "bom":
        wire = b"\xef\xbb\xbf" + wire
    elif variant == "trailing_json":
        wire += b"{}"
    else:
        changes = {"unknown": {"extra": True}, "version": {"version": m.SCOPE},
            "algorithm": {"algorithm": "HMAC-SHA256"}, "purpose": {"purpose": "policy"},
            "nested": {"nonce": {"value": "synthetic"}}, "bool_integer": {"writer_count": True},
            "null_integer": {"key_epoch": None}, "integer_string": {"key_epoch": "7"},
            "surrogate": {"nonce": "\ud800"}, "nonce_oversize": {"nonce": "a" * 257},
            "signature_upper": {"signature_hex": "A" * 128}}
        if variant in {"missing_default", "signature_missing"}:
            del document["writer_count" if variant == "missing_default" else "signature_hex"]
        else:
            document.update(changes[variant])
        wire = codec_bytes(document)
    assert m.epoch_wire_decode_offline_v3(wire, enabled=True, scope=m.EPOCH_REQUEST_SCOPE) is None


@pytest.mark.parametrize("wire", [None, "{}", bytearray(b"{}"), b"", b"[]", b"null", b"true",
    b'{"version":[]}', b"[" * 2000 + b"0" + b"]" * 2000])
def test_epoch_codec_v3_invalid_container_fails_closed(wire):
    assert m.epoch_wire_decode_offline_v3(wire, enabled=True, scope=m.EPOCH_REQUEST_SCOPE) is None


@pytest.mark.parametrize("scope,limit", [(m.EPOCH_REQUEST_SCOPE, 4243), (m.EPOCH_STATEMENT_SCOPE, 16531)])
def test_epoch_codec_v3_size_limit_precedes_json_parser(monkeypatch, scope, limit):
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("oversize input reached parser")
    monkeypatch.setattr(m.json, "loads", forbidden)
    assert m.epoch_wire_decode_offline_v3(b"x" * (limit + 1), enabled=True, scope=scope) is None
    assert calls == []


@pytest.mark.parametrize("field,value", [("writer_count", True), ("key_epoch", "7"), ("nonce", []),
    ("maintenance_only", 1), ("unexpected", "value")])
def test_epoch_codec_v3_types_and_keys_checked_before_dto(epoch_bundle, monkeypatch, field, value):
    options, _, _, _ = epoch_bundle
    wire = m.epoch_wire_encode_offline_v3(options["request"], enabled=True, scope=m.EPOCH_REQUEST_SCOPE)
    original = m.EpochRequestOfflineV3.__init__
    calls = []
    def tracked(self, *args, **kwargs):
        calls.append(True)
        original(self, *args, **kwargs)
    monkeypatch.setattr(m.EpochRequestOfflineV3, "__init__", tracked)
    changed = json.loads(wire) | {field: value}
    assert m.epoch_wire_decode_offline_v3(codec_bytes(changed), enabled=True, scope=m.EPOCH_REQUEST_SCOPE) is None
    assert calls == []
    assert m.epoch_wire_decode_offline_v3(wire, enabled=True, scope=m.EPOCH_REQUEST_SCOPE) is not None
    assert calls == [True]


@pytest.mark.parametrize("context", ["missing", "head", "different", "unsigned"])
def test_epoch_codec_v3_consumption_requires_exact_reservation_context(epoch_bundle, context):
    options, _, _, _ = epoch_bundle
    wire = m.epoch_wire_encode_offline_v3(options["consumption"], enabled=True, scope=m.EPOCH_STATEMENT_SCOPE)
    reservation = {"missing": None, "head": options["head"],
        "different": replace(options["reservation"], challenge="f" * 64),
        "unsigned": replace(options["reservation"], signature_hex=None)}[context]
    assert m.epoch_wire_decode_offline_v3(wire, enabled=True, scope=m.EPOCH_STATEMENT_SCOPE,
                                        reservation=reservation) is None


def test_epoch_codec_v3_decode_does_not_claim_authenticity(epoch_bundle):
    options, _, _, _ = epoch_bundle
    wire = m.epoch_wire_encode_offline_v3(options["request"], enabled=True, scope=m.EPOCH_REQUEST_SCOPE)
    changed = json.loads(wire) | {"nonce": "synthetic-tampered-but-valid-shape"}
    decoded = m.epoch_wire_decode_offline_v3(codec_bytes(changed), enabled=True, scope=m.EPOCH_REQUEST_SCOPE)
    assert decoded is not None  # Only grammar/shape, not a grant or signature verdict.
    assert m.epoch_evidence_signatures_consistent_offline_v3(**(options | {"request": decoded})) is False


@pytest.mark.parametrize("target,field,value", [
    ("policy", "revoked_key_ids", [["f" * 64]]), ("policy", "revoked_key_ids", [True]),
    ("policy", "revoked_key_ids", ["f" * 64, "f" * 64]),
    ("policy", "revoked_key_ids", ["f" * 64, "a" * 64]),
    ("head", "claim_sha256", "f" * 64), ("reservation", "claim_sha256", None),
    ("consumption", "reservation_sha256", "f" * 64),
    ("consumption", "committed_digest", "f" * 64), ("consumption", "reservation", {}),
])
def test_epoch_codec_v3_invalid_statement_fields(epoch_bundle, target, field, value):
    options, _, _, _ = epoch_bundle
    wire = m.epoch_wire_encode_offline_v3(options[target], enabled=True, scope=m.EPOCH_STATEMENT_SCOPE)
    changed = json.loads(wire) | {field: value}
    assert m.epoch_wire_decode_offline_v3(codec_bytes(changed), enabled=True, scope=m.EPOCH_STATEMENT_SCOPE,
        reservation=options["reservation"] if target == "consumption" else None) is None


@pytest.mark.parametrize("target", ["request", "policy", "head", "reservation", "consumption"])
def test_epoch_codec_v3_default_off_wrong_scope_and_unsigned(epoch_bundle, target):
    options, _, _, _ = epoch_bundle
    value = options[target]
    scope = codec_scope(target)
    assert m.epoch_wire_encode_offline_v3(value) is None
    assert m.epoch_wire_encode_offline_v3(value, enabled=1, scope=scope) is None
    assert m.epoch_wire_encode_offline_v3(value, enabled=True, scope=m.SCOPE) is None
    assert m.epoch_wire_encode_offline_v3(replace(value, signature_hex=None), enabled=True, scope=scope) is None
    wire = m.epoch_wire_encode_offline_v3(value, enabled=True, scope=scope)
    assert m.epoch_wire_decode_offline_v3(wire) is None
    assert m.epoch_wire_decode_offline_v3(wire, enabled=1, scope=scope) is None
    assert m.epoch_wire_decode_offline_v3(wire, enabled=True, scope=m.SCOPE) is None


def test_epoch_codec_v3_maximum_shapes_and_unexpected_context(epoch_bundle, wire):
    options, sign, _, _ = epoch_bundle
    request = replace(options["request"], nonce="\U0010ffff" * 256, key_epoch=2**53 - 1,
                      not_before_epoch_ms=2**53 - 2, expires_epoch_ms=2**53 - 1)
    unsigned = m.epoch_request_signing_message_offline_v3(request, enabled=True, scope=m.EPOCH_REQUEST_SCOPE)
    request = replace(request, signature_hex=wire[0].sign(unsigned).hex())
    policy = sign(replace(options["policy"], revoked_key_ids=tuple(f"{i:064x}" for i in range(128))))
    for value, scope, limit in ((request, m.EPOCH_REQUEST_SCOPE, 4243), (policy, m.EPOCH_STATEMENT_SCOPE, 16531)):
        encoded = m.epoch_wire_encode_offline_v3(value, enabled=True, scope=scope)
        assert len(encoded) <= limit
        assert m.epoch_wire_decode_offline_v3(encoded, enabled=True, scope=scope) == value
        assert m.epoch_wire_decode_offline_v3(encoded, enabled=True, scope=scope,
                                            reservation=options["reservation"]) is None


def receive_synthetic_epoch_messages(options, wires, observations, *, enabled=False,
                                     local_origin=0, local_budget_ms=5000):
    """TEST HARNESS ONLY: static crypto + injected time observations, never a permit.

    observations supply (local monotonic tick, trusted synthetic UTC lower/upper).
    No clock source is authenticated by this harness; no state survives a call.
    """
    if enabled is not True:
        return "off", ()
    decoded = {}
    for target in ("request", "policy", "head", "reservation", "consumption"):
        decoded[target] = m.epoch_wire_decode_offline_v3(wires.get(target), enabled=True,
            scope=codec_scope(target), reservation=decoded.get("reservation") if target == "consumption" else None)
        if decoded[target] is None:
            return "decode", ()
    if not m.epoch_evidence_signatures_consistent_offline_v3(**(options | decoded)):
        return "signatures", ()
    if (type(local_origin) is not int or local_origin < 0 or type(local_budget_ms) is not int
            or not 0 <= local_budget_ms <= 5000 or not observations):
        return "local_clock", ()
    request, policy, head, reservation = (decoded[k] for k in ("request", "policy", "head", "reservation"))
    starts = (request.not_before_epoch_ms, policy.issued_at_epoch_ms,
              head.not_before_epoch_ms, reservation.not_before_epoch_ms)
    ends = (request.expires_epoch_ms, policy.expires_epoch_ms, head.expires_epoch_ms, reservation.expires_epoch_ms)
    deadline, last = local_origin + local_budget_ms, local_origin
    durations = []
    for local_now, lower, upper in observations:
        if type(local_now) is not int or local_now < last:
            return "local_clock", tuple(durations)
        remaining = m.remaining_epoch_window_ms_offline_v2(enabled=True, scope=m.SCOPE,
            not_before_epoch_ms=max(starts), expires_epoch_ms=min(ends),
            now_lower_epoch_ms=lower, now_upper_epoch_ms=upper,
            local_remaining_ms=max(0, deadline - local_now), max_interval_width_ms=100)
        if remaining is None:
            return "time", tuple(durations)
        # Last admitted deadline is retained, never the original full budget.
        deadline = min(deadline, local_now + remaining)
        last = local_now
        durations.append(remaining)
    return "bounded", tuple(durations)


def synthetic_epoch_wires(options):
    return {target: m.epoch_wire_encode_offline_v3(options[target], enabled=True, scope=codec_scope(target))
            for target in ("request", "policy", "head", "reservation", "consumption")}


@pytest.mark.parametrize("origin", [0, 10000, 10**12])
@pytest.mark.parametrize("scenario,elapsed,lower,upper,budget,expected", [
    ("current", 100, 1002100, 1002150, 5000, ("bounded", (1850,))),
    ("one_ms_left", 1949, 1003949, 1003999, 5000, ("bounded", (1,))),
    ("before_reservation", 100, 1001900, 1001950, 5000, ("time", ())),
    ("cross_start", 100, 1001999, 1002001, 5000, ("time", ())),
    ("at_expiry", 2000, 1004000, 1004000, 5000, ("time", ())),
    ("historical", 100, 1010000, 1010050, 5000, ("time", ())),
    ("wide_uncertainty", 100, 1002100, 1002301, 5000, ("time", ())),
    ("verification_late", 1951, 1003951, 1004001, 5000, ("time", ())),
    ("local_budget_spent", 5000, 1002100, 1002150, 5000, ("time", ())),
    ("no_local_budget", 0, 1002100, 1002150, 0, ("time", ())),
])
def test_epoch_reception_v3_local_origins_and_current_validity(epoch_bundle, origin,
        scenario, elapsed, lower, upper, budget, expected):
    options, _, _, _ = epoch_bundle
    assert m.epoch_evidence_signatures_consistent_offline_v3(**options) is True
    observed = receive_synthetic_epoch_messages(options, synthetic_epoch_wires(options),
        [(origin + elapsed, lower, upper)], enabled=True, local_origin=origin, local_budget_ms=budget)
    assert observed == expected, scenario


@pytest.mark.parametrize("origin", [0, 10000, 10**12])
def test_epoch_reception_v3_rechecks_do_not_renew_admitted_deadline(epoch_bundle, origin):
    options, _, _, _ = epoch_bundle
    observations = [(origin + 100, 1002100, 1002150),
                    (origin + 1500, 1002050, 1002100),  # Synthetic civil-time correction backwards.
                    (origin + 1950, 1002050, 1002100)]
    result = receive_synthetic_epoch_messages(options, synthetic_epoch_wires(options), observations,
                                             enabled=True, local_origin=origin)
    assert result == ("time", (1850, 450))


@pytest.mark.parametrize("origin", [0, 10000, 10**12])
def test_epoch_reception_v3_local_monotonic_rollback_is_not_new_budget(epoch_bundle, origin):
    options, _, _, _ = epoch_bundle
    result = receive_synthetic_epoch_messages(options, synthetic_epoch_wires(options),
        [(origin + 100, 1002100, 1002150), (origin + 99, 1002200, 1002250)],
        enabled=True, local_origin=origin)
    assert result == ("local_clock", (1850,))


@pytest.mark.parametrize("fault,stage", [("malformed", "decode"), ("signature", "signatures"),
    ("pin", "signatures"), ("missing_reservation", "decode")])
def test_epoch_reception_v3_invalid_evidence_never_reaches_time_calculation(epoch_bundle, monkeypatch, fault, stage):
    options, _, _, _ = epoch_bundle
    wires = synthetic_epoch_wires(options)
    if fault == "malformed":
        wires["request"] += b"\n"
    elif fault == "signature":
        wires["request"] = codec_bytes(json.loads(wires["request"]) | {"nonce": "synthetic-tamper"})
    elif fault == "pin":
        options = options | {"expected_reservation_challenge": "f" * 64}
    else:
        del wires["reservation"]
    calls = []
    def forbidden(**kwargs):
        calls.append(True)
        raise AssertionError("unverified evidence reached temporal calculation")
    monkeypatch.setattr(m, "remaining_epoch_window_ms_offline_v2", forbidden)
    assert receive_synthetic_epoch_messages(options, wires, [(100, 1002100, 1002150)], enabled=True) == (stage, ())
    assert calls == []


def test_epoch_reception_v3_default_off_never_decodes(epoch_bundle, monkeypatch):
    options, _, _, _ = epoch_bundle
    wires = synthetic_epoch_wires(options)
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("disabled test harness reached decoder")
    monkeypatch.setattr(m, "epoch_wire_decode_offline_v3", forbidden)
    assert receive_synthetic_epoch_messages(options, wires, []) == ("off", ())
    assert receive_synthetic_epoch_messages(options, wires, [], enabled=1) == ("off", ())
    assert calls == []


def test_epoch_reception_v3_bounded_duration_is_not_consumption_evidence(epoch_bundle):
    options, _, _, _ = epoch_bundle
    wires = synthetic_epoch_wires(options)
    for _ in range(2):
        assert receive_synthetic_epoch_messages(options, wires, [(100, 1002100, 1002150)],
            enabled=True) == ("bounded", (1850,))
    # No ledger or trusted head is consulted. Repeatability explicitly rules out a permit claim.


@pytest.fixture
def epoch_emitter(epoch_bundle, tmp_path):
    options, sign, digest, pins = epoch_bundle
    ledger = m.SQLiteMaintenanceAuthorizationLedgerV1(tmp_path / "synthetic-epoch-emission.sqlite", enabled=True)
    ledger.provision()
    state = SimpleNamespace(policy=options["policy"], claims=set(), lock=threading.Lock(), events=[],
                            mono=100, lower=1002100, upper=1002150, fault=None)
    e = SimpleNamespace(options=options, sign=sign, digest=digest, pins=pins, ledger=ledger, state=state)
    def rows():
        with closing(sqlite3.connect(e.ledger._uri("ro"), uri=True)) as db:
            return dict(db.execute("SELECT claim_sha256,payload_sha256 FROM c3_maintenance_claims"))
    def commit(claim, payload):
        state.events.append("commit_attempt")
        if state.fault == "commit_rejected":
            return False
        if state.fault == "commit_exception":
            raise TimeoutError("synthetic pre-commit failure")
        result = e.ledger.consume_once(claim_sha256=claim, payload_sha256=payload)
        if result and state.fault == "commit_response_lost":
            raise TimeoutError("synthetic commit response lost")
        if result:
            state.events.append("commit_confirmed")
        return result
    def consumption_sign(receipt):
        # Independent read-back oracle at the signing boundary, not just a fake boolean.
        assert rows().get(receipt.reservation.claim_sha256) == receipt.committed_digest
        state.events.append("sign_consumption")
        if state.fault == "signer_exception":
            raise RuntimeError("synthetic signing failure")
        signed = sign(receipt)
        if state.fault == "signer_late":
            state.mono += 2000
            state.lower += 2000
            state.upper += 2000
        return signed
    e.rows, e.commit, e.consumption_sign = rows, commit, consumption_sign
    return e


def emit_synthetic_epoch_receipt(e, wire, *, enabled=False):
    """TEST HARNESS ONLY. In-memory witness assumption plus temporary SQLite.

    Not a service/production consumer; no fabricated consumption receipt is reused.
    Every failed post-reservation path leaves the claim burned. No compensation.
    """
    if enabled is not True:
        return None
    try:
        o, state = e.options, e.state
        request = m.epoch_wire_decode_offline_v3(wire, enabled=True, scope=m.EPOCH_REQUEST_SCOPE)
        if not m.epoch_request_signature_verified_offline_v3(request, enabled=True, scope=m.EPOCH_REQUEST_SCOPE,
                public_key_bytes=o["public_keys"]["request"], expected_key_epoch=o["key_epochs"]["request"],
                expected_namespace=o["expected_namespace"], expected_root=o["expected_root"]):
            return None
        policy = state.policy
        if not m.epoch_statement_signature_verified_offline_v3(policy, **e.pins("policy")):
            return None
        if set(policy.revoked_key_ids).intersection(hashlib.sha256(k).hexdigest() for k in o["public_keys"].values()):
            return None
        payload = hashlib.sha256(m.epoch_request_signing_message_offline_v3(
            request, enabled=True, scope=m.EPOCH_REQUEST_SCOPE)).hexdigest()
        claim = m.epoch_request_claim_offline_v3(request, enabled=True, scope=m.EPOCH_REQUEST_SCOPE)
        start = max(request.not_before_epoch_ms, policy.issued_at_epoch_ms, state.lower)
        end = min(request.expires_epoch_ms, policy.expires_epoch_ms, state.upper + 1000)
        head = e.sign(m.EpochAnchorOfflineV3("anchor_head", o["expected_namespace"], o["expected_instance"],
            policy.generation, e.digest(policy), payload, o["expected_head_challenge"], start, end,
            hashlib.sha256(o["public_keys"]["anchor"]).hexdigest(), o["key_epochs"]["anchor"]))
        deadline, last = state.mono + 5000, state.mono
        def checkpoint():
            nonlocal deadline, last
            if state.mono < last:
                return False
            remaining = m.remaining_epoch_window_ms_offline_v2(enabled=True, scope=m.SCOPE,
                not_before_epoch_ms=start, expires_epoch_ms=end,
                now_lower_epoch_ms=state.lower, now_upper_epoch_ms=state.upper,
                local_remaining_ms=max(0, deadline - state.mono), max_interval_width_ms=100)
            if remaining is None:
                return False
            deadline, last = min(deadline, state.mono + remaining), state.mono
            return True
        if not checkpoint():
            return None
        if state.fault == "policy_before_reserve":
            state.policy = e.sign(replace(policy, generation=policy.generation + 1))
        with state.lock:
            if e.digest(state.policy) != head.policy_sha256:
                return None
            identity = (head.namespace, claim)
            if identity in state.claims:
                state.events.append("replay_blocked")
                return None
            state.claims.add(identity)
            state.events.append("reserved")
        if state.fault == "reservation_response_lost":
            raise TimeoutError("synthetic reservation response lost")
        reservation = e.sign(replace(head, purpose="anchor_reserve", claim_sha256=claim,
                                     challenge=o["expected_reservation_challenge"], signature_hex=None))
        if not checkpoint():
            return None
        committed_digest = e.digest(reservation)
        if e.commit(claim, committed_digest) is not True:
            return None
        if state.fault == "policy_after_commit":
            state.policy = e.sign(replace(policy, generation=policy.generation + 1))
        if state.fault == "commit_late":
            state.mono += 2000
            state.lower += 2000
            state.upper += 2000
        if not checkpoint() or e.digest(state.policy) != head.policy_sha256:
            return None
        receipt = e.consumption_sign(m.EpochConsumptionOfflineV3(reservation, committed_digest,
            hashlib.sha256(o["public_keys"]["consumption"]).hexdigest(), o["key_epochs"]["consumption"]))
        evidence = o | dict(request=request, policy=policy, head=head, reservation=reservation, consumption=receipt)
        if (not m.epoch_evidence_signatures_consistent_offline_v3(**evidence)
                or not checkpoint() or e.digest(state.policy) != head.policy_sha256):
            return None
        if state.fault == "response_lost":
            return None
        state.events.append("response")
        return synthetic_epoch_wires(evidence)
    except Exception:
        return None


@pytest.mark.parametrize("fault,committed,sign_attempted", [
    (None, True, True), ("reservation_response_lost", False, False),
    ("commit_rejected", False, False), ("commit_exception", False, False),
    ("commit_response_lost", True, False), ("policy_after_commit", True, False),
    ("commit_late", True, False), ("signer_exception", True, True),
    ("signer_late", True, True), ("response_lost", True, True),
])
def test_epoch_emission_v3_order_and_post_reservation_failures(epoch_emitter, fault, committed, sign_attempted):
    e = epoch_emitter
    e.state.fault = fault
    wire = m.epoch_wire_encode_offline_v3(e.options["request"], enabled=True, scope=m.EPOCH_REQUEST_SCOPE)
    packet = emit_synthetic_epoch_receipt(e, wire, enabled=True)
    assert (packet is not None) is (fault is None)
    assert len(e.state.claims) == 1 and len(e.rows()) == int(committed)
    assert e.state.events.count("sign_consumption") == int(sign_attempted)
    if sign_attempted:
        assert e.state.events.index("reserved") < e.state.events.index("commit_confirmed") < e.state.events.index("sign_consumption")
    if packet:
        assert receive_synthetic_epoch_messages(e.options, packet, [(100, 1002100, 1002150)],
            enabled=True) == ("bounded", (1000,))
    # A new local ledger object / retry cannot reissue a burned external identity.
    before = (dict(e.rows()), e.state.events.count("sign_consumption"))
    e.ledger = m.SQLiteMaintenanceAuthorizationLedgerV1(e.ledger._database, enabled=True)
    e.state.fault = None
    assert emit_synthetic_epoch_receipt(e, wire, enabled=True) is None
    assert (e.rows(), e.state.events.count("sign_consumption")) == before
    assert len(e.state.claims) == 1
    assert e.state.events[-1] == "replay_blocked"


@pytest.mark.parametrize("fault", ["invalid_signature", "wrong_root", "policy_before_reserve", "revoked"])
def test_epoch_emission_v3_invalid_input_never_commits(epoch_emitter, fault):
    e = epoch_emitter
    wire = m.epoch_wire_encode_offline_v3(e.options["request"], enabled=True, scope=m.EPOCH_REQUEST_SCOPE)
    if fault == "invalid_signature":
        wire = codec_bytes(json.loads(wire) | {"nonce": "synthetic-invalid"})
    elif fault == "wrong_root":
        e.options = e.options | {"expected_root": "f" * 64}
    elif fault == "revoked":
        e.state.policy = e.sign(replace(e.state.policy, revoked_key_ids=(e.options["request"].key_id,)))
    else:
        e.state.fault = fault
    assert emit_synthetic_epoch_receipt(e, wire, enabled=True) is None
    assert not e.state.claims and not e.rows() and not e.state.events


def test_epoch_emission_v3_concurrent_calls_issue_one_receipt(epoch_emitter):
    e = epoch_emitter
    wire = m.epoch_wire_encode_offline_v3(e.options["request"], enabled=True, scope=m.EPOCH_REQUEST_SCOPE)
    barrier = threading.Barrier(4, timeout=5)
    def attempt(_):
        barrier.wait()
        return emit_synthetic_epoch_receipt(e, wire, enabled=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        packets = list(pool.map(attempt, range(4)))
    assert sum(p is not None for p in packets) == 1
    assert len(e.state.claims) == len(e.rows()) == 1
    assert e.state.events.count("commit_confirmed") == e.state.events.count("sign_consumption") == 1


@pytest.mark.parametrize("wrong_row", [False, True])
def test_epoch_emission_v3_independent_oracle_rejects_false_commit_confirmation(epoch_emitter, wrong_row):
    e = epoch_emitter
    wire = m.epoch_wire_encode_offline_v3(e.options["request"], enabled=True, scope=m.EPOCH_REQUEST_SCOPE)
    def dishonest_commit(claim, payload):
        if wrong_row:
            assert e.ledger.consume_once(claim_sha256=claim, payload_sha256="f" * 64)
        e.state.events.append("commit_confirmed")
        return True
    e.commit = dishonest_commit
    assert emit_synthetic_epoch_receipt(e, wire, enabled=True) is None
    assert len(e.state.claims) == 1 and len(e.rows()) == int(wrong_row)
    assert "sign_consumption" not in e.state.events
    # This is a test oracle assertion, NOT a new production signing interlock.


@pytest.mark.parametrize("restore_witness", [False, True])
def test_epoch_emission_v3_restore_boundary_explicit(epoch_emitter, restore_witness):
    e = epoch_emitter
    wire = m.epoch_wire_encode_offline_v3(e.options["request"], enabled=True, scope=m.EPOCH_REQUEST_SCOPE)
    with closing(sqlite3.connect(":memory:")) as backup:
        with closing(sqlite3.connect(e.ledger._uri("ro"), uri=True)) as source:
            source.backup(backup)
        assert emit_synthetic_epoch_receipt(e, wire, enabled=True) is not None
        with closing(sqlite3.connect(e.ledger._uri("rw"), uri=True)) as target:
            backup.backup(target)  # Only this test's temporary synthetic database.
    assert e.rows() == {}
    if restore_witness:
        e.state.claims = set()  # Deliberately unsafe negative control, NOT an implementation recommendation.
    packet = emit_synthetic_epoch_receipt(e, wire, enabled=True)
    assert (packet is not None) is restore_witness
    assert e.state.events.count("sign_consumption") == (2 if restore_witness else 1)


def test_epoch_emission_v3_default_off_without_any_dependency_access():
    assert emit_synthetic_epoch_receipt(object(), object()) is None
    assert emit_synthetic_epoch_receipt(object(), object(), enabled=1) is None
