from __future__ import annotations

import hashlib
import hmac
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2 as adapters_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_kms_hmac_verification_adapter_v2 as kms_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_harness_v2 as harness_v2


_ARN = "arn:aws:kms:us-west-2:111122223333:key/1234abcd-12ab-34cd-56ef-1234567890ab"
_KEY = b"synthetic-kms-hmac-key-never-used-outside-tests"
_MESSAGE = b"a" * 64
_MAC = hmac.new(_KEY, _MESSAGE, hashlib.sha256).digest()


class FakeKmsClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.response_override: object = None
        self.raise_error = False

    def verify_mac(self, **request: object) -> object:
        self.calls.append(request)
        if self.raise_error:
            raise TimeoutError("synthetic KMS unavailable")
        if self.response_override is not None:
            return self.response_override
        return {
            "KeyId": request["KeyId"],
            "MacAlgorithm": request["MacAlgorithm"],
            "MacValid": hmac.compare_digest(
                hmac.new(_KEY, request["Message"], hashlib.sha256).digest(),
                request["Mac"],
            ),
        }


def _provider(client: object) -> kms_v2.KmsRootHmacVerificationProviderV2:
    return kms_v2.KmsRootHmacVerificationProviderV2(
        kms_v2.KmsRootHmacVerificationConfigV2(
            enabled=True,
            scope_attestation=adapters_v2.PRODUCTION_AUTHORITY_ADAPTERS_EXPLICIT_DEPENDENCY_SCOPE_V2,
            key_arn=_ARN,
            expected_client_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    client
                )
            ),
        ),
        client=client,
    )


def _verify(provider: kms_v2.KmsRootHmacVerificationProviderV2, **changes: object) -> bool:
    request = {
        "key_id_sha256": kms_v2.kms_root_hmac_key_id_sha256_v2(_ARN),
        "message": _MESSAGE,
        "mac": _MAC,
        "mac_algorithm": "HMAC_SHA_256",
    }
    return provider.verify_root_hmac_v2(**{**request, **changes})


def test_key_id_is_bound_to_full_immutable_arn() -> None:
    assert kms_v2.kms_root_hmac_key_id_sha256_v2(_ARN) == hashlib.sha256(
        _ARN.encode("ascii")
    ).hexdigest()
    for invalid in (
        "alias/c3-root", "arn:aws:kms:us-west-2:111122223333:alias/c3-root",
        "arn:aws:kms:us-west-2:111122223333:key/not-a-key-id",
        "arn:aws:kms:us-west-2:111122223333:key/1234ABCD-12ab-34cd-56ef-1234567890ab",
        None,
    ):
        with pytest.raises(ValueError, match="C3_KMS_ROOT_KEY_ARN_INVALID"):
            kms_v2.kms_root_hmac_key_id_sha256_v2(invalid)


def test_default_off_and_invalid_binding_never_call_client() -> None:
    client = FakeKmsClient()
    dormant = kms_v2.KmsRootHmacVerificationProviderV2(client=client)
    assert _verify(dormant) is False
    assert repr(dormant) == "KmsRootHmacVerificationProviderV2(<protected>)"
    missing_pin = kms_v2.KmsRootHmacVerificationProviderV2(
        kms_v2.KmsRootHmacVerificationConfigV2(
            enabled=True,
            scope_attestation=adapters_v2.PRODUCTION_AUTHORITY_ADAPTERS_EXPLICIT_DEPENDENCY_SCOPE_V2,
            key_arn=_ARN,
        ),
        client=client,
    )
    assert _verify(missing_pin) is False
    assert client.calls == []


def test_valid_fake_kms_verdict_composes_with_remote_root_verifier() -> None:
    client = FakeKmsClient()
    provider = _provider(client)
    verifier = adapters_v2.InjectedRootAuthorityVerifierV2(
        adapters_v2.InjectedRootAuthorityVerifierConfigV2(
            enabled=True,
            scope_attestation=adapters_v2.PRODUCTION_AUTHORITY_ADAPTERS_EXPLICIT_DEPENDENCY_SCOPE_V2,
            expected_key_provider_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    provider
                )
            ),
            verification_mode=adapters_v2.ROOT_HMAC_REMOTE_VERDICT_MODE_V2,
        ),
        key_provider=provider,
    )

    assert verifier.verify_root_authority_signature_v2(
        key_id_sha256=kms_v2.kms_root_hmac_key_id_sha256_v2(_ARN),
        payload_sha256=_MESSAGE.decode("ascii"),
        signature_sha256=_MAC.hex(),
    ) is True
    assert client.calls == [{
        "KeyId": _ARN,
        "Message": _MESSAGE,
        "Mac": _MAC,
        "MacAlgorithm": "HMAC_SHA_256",
    }]
    assert not hasattr(provider, "resolve_root_hmac_key_v2")


@pytest.mark.parametrize("change", [
    {"key_id_sha256": "0" * 64},
    {"key_id_sha256": "A" * 64},
    {"message": b"A" * 64},
    {"message": b"a" * 63},
    {"mac": b"a" * 31},
    {"mac_algorithm": "HMAC_SHA_512"},
    {"mac_algorithm": b"HMAC_SHA_256"},
])
def test_malformed_or_wrong_pins_fail_before_client_call(change: dict) -> None:
    client = FakeKmsClient()
    assert _verify(_provider(client), **change) is False
    assert client.calls == []


@pytest.mark.parametrize("response", [
    {"KeyId": _ARN, "MacAlgorithm": "HMAC_SHA_256", "MacValid": False},
    {"KeyId": _ARN, "MacAlgorithm": "HMAC_SHA_256", "MacValid": 1},
    {"KeyId": _ARN, "MacAlgorithm": "HMAC_SHA_256"},
    {"KeyId": "arn:aws:kms:us-west-2:111122223333:key/00000000-0000-0000-0000-000000000000",
     "MacAlgorithm": "HMAC_SHA_256", "MacValid": True},
    {"KeyId": _ARN, "MacAlgorithm": "HMAC_SHA_512", "MacValid": True},
    {"KeyId": _ARN.encode("ascii"), "MacAlgorithm": "HMAC_SHA_256", "MacValid": True},
    True,
])
def test_ambiguous_or_mismatched_kms_response_fails_closed(response: object) -> None:
    client = FakeKmsClient()
    client.response_override = response
    assert _verify(_provider(client)) is False
    assert len(client.calls) == 1


def test_wrong_mac_transport_error_and_client_swap_fail_closed() -> None:
    client = FakeKmsClient()
    provider = _provider(client)
    assert _verify(provider, mac=b"0" * 32) is False
    client.raise_error = True
    assert _verify(provider) is False
    assert len(client.calls) == 2
    provider._client = FakeKmsClient()
    assert _verify(provider) is False
    assert len(provider._client.calls) == 0


def _recovery_context(root: Path, *, revoked: bool = False) -> dict:
    # Only Windows logical tests bypass directory fsync; Linux uses the real call.
    directory_fsync = (lambda _path: None) if os.name == "nt" else None
    return harness_v2.build_authenticated_persistent_authority_production_adapters_context_v2(
        root, revoked=revoked, remote_hmac=True,
        synthetic_kms_key_arn=_ARN, lease_directory_fsync=directory_fsync,
    )


def _recover(values: dict) -> dict:
    with values["maintenance_coordinator"].maintenance_lease() as permit:
        return values["boundary"](asdict(permit))


def test_synthetic_kms_verdict_reaches_full_recovery_boundary() -> None:
    with tempfile.TemporaryDirectory(prefix="c3_kms_full_recovery_v2_") as root:
        values = _recovery_context(Path(root))
        assert values["attestation"]["key_id_sha256"] == (
            kms_v2.kms_root_hmac_key_id_sha256_v2(_ARN)
        )

        result = _recover(values)

        assert result["ok"] is True
        assert result["root_signature_verified"] is True
        assert result["multistore_recovery_verified"] is True
        assert result["production_ready"] is False
        assert result["live_allowed"] is False
        assert values["transaction_port"].call_count == 1
        assert values["resolved_port"].call_count == 1
        assert len(values["kms_client"].calls) == 1
        assert values["kms_client"].calls[0]["KeyId"] == _ARN


@pytest.mark.parametrize("response", [
    {"KeyId": _ARN, "MacAlgorithm": "HMAC_SHA_256", "MacValid": False},
    {"KeyId": "wrong-key", "MacAlgorithm": "HMAC_SHA_256", "MacValid": True},
    {"KeyId": _ARN, "MacAlgorithm": "HMAC_SHA_256", "MacValid": 1},
    "transport-error",
])
def test_synthetic_kms_failure_blocks_recovery_ports(response: object) -> None:
    with tempfile.TemporaryDirectory(prefix="c3_kms_blocked_recovery_v2_") as root:
        values = _recovery_context(Path(root))
        if response == "transport-error":
            values["kms_client"].raise_error = True
        else:
            values["kms_client"].response_override = response

        result = _recover(values)

        assert result["ok"] is False
        assert result["reason"] == "PERSISTENT_ROOT_AUTHORITY_NOT_AUTHENTICATED"
        assert values["transaction_port"].call_count == 0
        assert values["resolved_port"].call_count == 0
        assert values["prepared"].call_count == 0


def test_synthetic_kms_valid_verdict_still_respects_revocation() -> None:
    with tempfile.TemporaryDirectory(prefix="c3_kms_revoked_recovery_v2_") as root:
        values = _recovery_context(Path(root), revoked=True)

        result = _recover(values)

        assert result["ok"] is False
        assert result["reason"] == "PERSISTENT_ROOT_AUTHORITY_REVOKED"
        assert len(values["kms_client"].calls) == 1
        assert values["transaction_port"].call_count == 0
        assert values["resolved_port"].call_count == 0


def test_synthetic_kms_mode_must_be_explicit_before_storage_setup() -> None:
    with tempfile.TemporaryDirectory(prefix="c3_kms_mode_reject_v2_") as root:
        root_path = Path(root)
        with pytest.raises(ValueError, match="SYNTHETIC_KMS_REQUIRES_REMOTE_HMAC_MODE"):
            harness_v2.build_authenticated_persistent_authority_production_adapters_context_v2(
                root_path, synthetic_kms_key_arn=_ARN,
            )
        assert list(root_path.iterdir()) == []
