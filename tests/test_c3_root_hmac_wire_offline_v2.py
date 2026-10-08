"""Characterize the existing root verifier seam, not an AWS adapter.

Public synthetic material only; no SDK, credential lookup, HTTP or filesystem.
The fake below represents verification semantics, NOT an authenticated service.
"""

import hashlib
import hmac
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import hashes, hmac as independent_hmac

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as root


PUBLIC_TEST_KEY = b"C3-ROOT-HMAC-PUBLIC-SYNTHETIC-ONLY!"


def mac(message):
    # Separate implementation from the reference adapter's stdlib hmac.
    signer = independent_hmac.HMAC(PUBLIC_TEST_KEY, hashes.SHA256())
    signer.update(message)
    return signer.finalize()


@pytest.fixture
def attestation():
    value = {
        "attestation_version": root.AUTHENTICATED_ROOT_AUTHORITY_ATTESTATION_VERSION_V2,
        "root_identity_sha256": "1" * 64,
        "storage_binding_sha256": "2" * 64,
        "key_id_sha256": "3" * 64,
        "key_epoch": 1,
        "previous_attestation_sha256": None,
        "issued_at_epoch": 100,
        "expires_at_epoch": 200,
        "signature_algorithm": root.ROOT_AUTHORITY_SIGNATURE_ALGORITHM_V2,
    }
    # Literal, independent serialization oracle. No production issuer involved.
    message = ('{"attestation_version":"C3_AUTHENTICATED_ROOT_AUTHORITY_ATTESTATION_V2",'
               '"expires_at_epoch":200,"issued_at_epoch":100,"key_epoch":1,'
               '"key_id_sha256":"' + '3' * 64 + '","previous_attestation_sha256":null,'
               '"root_identity_sha256":"' + '1' * 64 + '",'
               '"signature_algorithm":"HMAC-SHA256-REFERENCE",'
               '"storage_binding_sha256":"' + '2' * 64 + '"}').encode("utf-8")
    digest = hashlib.sha256(message).hexdigest()
    assert digest == root.root_authority_signature_payload_sha256_v2(value)
    value["signature_sha256"] = mac(digest.encode("ascii")).hex()
    value["attestation_sha256"] = root.authenticated_root_authority_attestation_sha256_v2(value)
    return value


def test_root_hmac_existing_seam_needs_verdict_not_key_export(attestation):
    calls = []

    def verify(**request):
        calls.append(request)
        assert request["key_id_sha256"] == "3" * 64
        message = request["payload_sha256"].encode("ascii")
        tag = bytes.fromhex(request["signature_sha256"])
        assert len(message) == 64 and len(tag) == 32
        checker = independent_hmac.HMAC(PUBLIC_TEST_KEY, hashes.SHA256())
        checker.update(message)
        checker.verify(tag)
        return True

    verifier = SimpleNamespace(verify_root_authority_signature_v2=verify)
    assert not hasattr(verifier, "resolve_root_hmac_key_v2")
    assert root.authenticated_root_authority_attestation_verified_v2(attestation, verifier) is True
    assert len(calls) == 1
    assert attestation["signature_sha256"] == hmac.new(
        PUBLIC_TEST_KEY, calls[0]["payload_sha256"].encode("ascii"), hashlib.sha256).hexdigest()


@pytest.mark.parametrize("change", ["raw_digest", "double_hash", "newline", "different_key"])
def test_root_hmac_message_and_key_are_not_interchangeable(attestation, change):
    digest = root.root_authority_signature_payload_sha256_v2(attestation)
    message = digest.encode("ascii")
    modified = {"raw_digest": bytes.fromhex(digest),
                "double_hash": hashlib.sha256(message).digest(),
                "newline": message + b"\n", "different_key": message}[change]
    key = PUBLIC_TEST_KEY if change != "different_key" else b"unrelated-public-test-key-material"
    tag = hmac.new(key, modified, hashlib.sha256).hexdigest()
    assert not hmac.compare_digest(tag, attestation["signature_sha256"])


@pytest.mark.parametrize("verdict", [False, None, 1, "true", {"MacValid": True}])
def test_root_hmac_seam_requires_exact_boolean_verdict(attestation, verdict):
    verifier = SimpleNamespace(verify_root_authority_signature_v2=lambda **_: verdict)
    assert root.authenticated_root_authority_attestation_verified_v2(attestation, verifier) is False


def test_root_hmac_transport_exception_fails_closed(attestation):
    def timeout(**_):
        raise TimeoutError("synthetic timeout; no transport was opened")

    assert root.authenticated_root_authority_attestation_verified_v2(
        attestation, SimpleNamespace(verify_root_authority_signature_v2=timeout)) is False


@pytest.mark.parametrize("field,value", [
    ("signature_algorithm", "Ed25519"), ("signature_sha256", "a" * 128),
    ("attestation_version", "C3_AUTHENTICATED_ROOT_AUTHORITY_ATTESTATION_V3"),
])
def test_root_hmac_no_public_protocol_fallback(attestation, field, value):
    attestation[field] = value
    attestation["attestation_sha256"] = root.authenticated_root_authority_attestation_sha256_v2(attestation)

    def forbidden(**_):
        pytest.fail("invalid format must be rejected before verifier invocation")

    assert root.authenticated_root_authority_attestation_verified_v2(
        attestation, SimpleNamespace(verify_root_authority_signature_v2=forbidden)) is False
