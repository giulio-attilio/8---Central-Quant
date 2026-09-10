from __future__ import annotations

import json
import tempfile
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_harness_v2 as harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2 as adapters_v2


def _permit() -> dict:
    return {
        "maintenance_epoch": hash_v2.stable_sha256_v2(
            {"maintenance_epoch": "production-adapters-test"}
        ),
        "state": "QUIESCED",
        "lock_namespace_sha256": hash_v2.stable_sha256_v2(
            {"lock_namespace": "production-adapters-test"}
        ),
        "registered_writer_count": 19,
        "inflight_mutations": 0,
        "shared_lock_acquired": True,
    }


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

        result = values["boundary"](_permit())

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

        result = values["boundary"](_permit())

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

        result = values["boundary"](_permit())

        assert result["ok"] is False
        assert result["reason"] == "PERSISTENT_MULTISTORE_RECOVERY_FAILED_CLOSED"
        assert values["transaction_port"].call_count == 1
        assert values["resolved_port"].call_count == 0
        assert values["prepared"].call_count == 0
