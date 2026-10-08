from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as authority_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_harness_v2 as harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2 as adapters_v2


def _recover(values) -> dict:
    with values["maintenance_coordinator"].maintenance_lease() as permit:
        return values["boundary"](asdict(permit))


def _remote_context(root: Path, *, revoked: bool = False) -> dict:
    # Windows cannot fsync a directory. This substitution is only for logical
    # integration tests; it makes no durability claim about the lease store.
    directory_fsync = (lambda _path: None) if os.name == "nt" else None
    return harness_v2.build_authenticated_persistent_authority_production_adapters_context_v2(
        root, revoked=revoked, remote_hmac=True,
        lease_directory_fsync=directory_fsync,
    )


def test_dormant_adapter_bundle_is_side_effect_free_and_protected() -> None:
    bundle = adapters_v2.build_dormant_authenticated_persistent_authority_production_adapters_v2()

    assert bundle.root_state_provider.snapshot()["default_off"] is True
    assert bundle.root_state_provider.snapshot()["filesystem_accessed"] is False
    assert bundle.root_authority_verifier.verify_root_authority_signature_v2(
        key_id_sha256="0" * 64,
        payload_sha256="1" * 64,
        signature_sha256="2" * 64,
    ) is False
    assert repr(bundle) == (
        "DormantAuthenticatedPersistentAuthorityProductionAdaptersV2(<protected>)"
    )


def test_four_production_shaped_adapters_pass_temporary_harness() -> None:
    result = harness_v2.run_authenticated_persistent_authority_production_adapters_harness_v2()

    assert result["ok"] is True
    assert result["four_adapters_verified"] is True
    assert result["temporary_storage_removed"] is True
    assert result["real_registry_accessed"] is False
    assert result["network_accessed"] is False
    assert result["broker_called"] is False
    assert result["no_order_sent"] is True
    assert result["production_ready"] is False
    assert result["live_allowed"] is False


def test_corrupted_persistent_root_envelope_fails_before_other_adapters() -> None:
    with tempfile.TemporaryDirectory(prefix="c3_adapters_corrupt_root_v2_") as root:
        root_path = Path(root)
        values = harness_v2.build_authenticated_persistent_authority_production_adapters_context_v2(
            root_path
        )
        path = root_path / "c3_root_authority_state_v2.json"
        envelope = json.loads(path.read_text(encoding="utf-8"))
        envelope["generation"] = 2
        path.write_text(json.dumps(envelope), encoding="utf-8")

        result = _recover(values)

        assert result["ok"] is False
        assert result["reason"] == "PERSISTENT_ROOT_AUTHORITY_READ_FAILED_CLOSED"
        assert values["transaction_port"].call_count == 0
        assert values["resolved_port"].call_count == 0
        assert values["prepared"].call_count == 0


def test_persistent_revocation_blocks_both_store_recovery_ports() -> None:
    with tempfile.TemporaryDirectory(prefix="c3_adapters_revoked_v2_") as root:
        values = harness_v2.build_authenticated_persistent_authority_production_adapters_context_v2(
            Path(root), revoked=True
        )

        result = _recover(values)

        assert result["ok"] is False
        assert result["reason"] == "PERSISTENT_ROOT_AUTHORITY_REVOKED"
        assert result["root_revoked"] is True
        assert values["transaction_port"].call_count == 0
        assert values["resolved_port"].call_count == 0
        assert values["prepared"].call_count == 0


def test_transaction_store_failure_prevents_resolved_store_and_bridge() -> None:
    with tempfile.TemporaryDirectory(prefix="c3_adapters_store_failure_v2_") as root:
        root_path = Path(root)
        values = harness_v2.build_authenticated_persistent_authority_production_adapters_context_v2(
            root_path
        )
        transaction_path = root_path / "transaction_recovery_state.json"
        transaction_path.write_text(
            json.dumps({"state": "PREPARED", "transactions_remaining": 1}),
            encoding="utf-8",
        )

        result = _recover(values)

        assert result["ok"] is False
        assert result["reason"] == "PERSISTENT_MULTISTORE_RECOVERY_FAILED_CLOSED"
        assert values["transaction_port"].call_count == 1
        assert values["resolved_port"].call_count == 0
        assert values["prepared"].call_count == 0


def test_remote_hmac_verdict_composes_with_synthetic_recovery() -> None:
    with tempfile.TemporaryDirectory(prefix="c3_remote_root_recovery_v2_") as root:
        values = _remote_context(Path(root))
        provider = values["key_provider"]
        assert not hasattr(provider, "resolve_root_hmac_key_v2")

        result = _recover(values)

        assert result["ok"] is True
        assert result["root_signature_verified"] is True
        assert result["multistore_recovery_verified"] is True
        assert result["production_ready"] is False
        assert result["live_allowed"] is False
        assert values["transaction_port"].call_count == 1
        assert values["resolved_port"].call_count == 1
        assert len(provider.calls) == 1
        key_id, message, mac, algorithm = provider.calls[0]
        assert key_id == values["attestation"]["key_id_sha256"]
        assert message == authority_v2.root_authority_signature_payload_sha256_v2(
            values["attestation"]
        ).encode("ascii")
        assert mac == bytes.fromhex(values["attestation"]["signature_sha256"])
        assert algorithm == "HMAC_SHA_256"


def test_remote_hmac_rejection_and_transport_failure_block_recovery() -> None:
    for case in (False, 1, {"MacValid": True}, "error"):
        with tempfile.TemporaryDirectory(prefix="c3_remote_root_reject_v2_") as root:
            values = _remote_context(Path(root))
            provider = values["key_provider"]
            if case == "error":
                provider.raise_error = True
            else:
                provider.verdict = case

            result = _recover(values)

            assert result["ok"] is False
            assert result["reason"] == "PERSISTENT_ROOT_AUTHORITY_NOT_AUTHENTICATED"
            assert len(provider.calls) == 1
            assert values["transaction_port"].call_count == 0
            assert values["resolved_port"].call_count == 0
            assert values["prepared"].call_count == 0


def test_remote_hmac_revocation_blocks_recovery_after_valid_verdict() -> None:
    with tempfile.TemporaryDirectory(prefix="c3_remote_root_revoked_v2_") as root:
        values = _remote_context(Path(root), revoked=True)

        result = _recover(values)

        assert result["reason"] == "PERSISTENT_ROOT_AUTHORITY_REVOKED"
        assert len(values["key_provider"].calls) == 1
        assert values["transaction_port"].call_count == 0
        assert values["resolved_port"].call_count == 0


def test_remote_hmac_rejects_malformed_inputs_before_verification() -> None:
    with tempfile.TemporaryDirectory(prefix="c3_remote_root_shape_v2_") as root:
        values = _remote_context(Path(root))
        verifier = values["verifier"]
        attestation = values["attestation"]
        valid = dict(
            key_id_sha256=attestation["key_id_sha256"],
            payload_sha256="1" * 64,
            signature_sha256=attestation["signature_sha256"],
        )
        for replacement in ({"payload_sha256": "1" * 63},
                            {"key_id_sha256": "A" * 64},
                            {"signature_sha256": "z" * 64}):
            assert verifier.verify_root_authority_signature_v2(
                **{**valid, **replacement}
            ) is False
        assert values["key_provider"].calls == []


def test_remote_hmac_rejects_wrong_tag_and_unknown_mode_without_fallback() -> None:
    with tempfile.TemporaryDirectory(prefix="c3_remote_root_no_fallback_v2_") as root:
        values = _remote_context(Path(root))
        attestation = values["attestation"]
        provider = values["key_provider"]
        request = dict(
            key_id_sha256=attestation["key_id_sha256"],
            payload_sha256=authority_v2.root_authority_signature_payload_sha256_v2(attestation),
            signature_sha256="0" * 64,
        )
        assert values["verifier"].verify_root_authority_signature_v2(**request) is False
        assert len(provider.calls) == 1
        unknown = adapters_v2.InjectedRootAuthorityVerifierV2(
            adapters_v2.InjectedRootAuthorityVerifierConfigV2(
                enabled=True,
                scope_attestation=adapters_v2.PRODUCTION_AUTHORITY_ADAPTERS_EXPLICIT_DEPENDENCY_SCOPE_V2,
                expected_key_provider_object_identity_sha256=harness_v2._object_identity(provider),
                verification_mode="UNRECOGNIZED_MODE",
            ),
            key_provider=provider,
        )
        assert unknown.verify_root_authority_signature_v2(**request) is False
        assert len(provider.calls) == 1


def test_local_hmac_mode_still_recovers_only_in_synthetic_harness() -> None:
    with tempfile.TemporaryDirectory(prefix="c3_local_root_compat_v2_") as root:
        directory_fsync = (lambda _path: None) if os.name == "nt" else None
        values = harness_v2.build_authenticated_persistent_authority_production_adapters_context_v2(
            Path(root), lease_directory_fsync=directory_fsync,
        )

        result = _recover(values)

        assert result["ok"] is True
        assert result["multistore_recovery_verified"] is True
        assert result["live_allowed"] is False
