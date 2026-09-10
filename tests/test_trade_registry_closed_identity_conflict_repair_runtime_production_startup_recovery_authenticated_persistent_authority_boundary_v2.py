from __future__ import annotations

import tempfile
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_harness_v2 as harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_v2 as boundary_v2


def _permit() -> dict:
    return {
        "maintenance_epoch": hash_v2.stable_sha256_v2(
            {"maintenance_epoch": "boundary-test"}
        ),
        "state": "QUIESCED",
        "lock_namespace_sha256": hash_v2.stable_sha256_v2(
            {"lock_namespace": "boundary-test"}
        ),
        "registered_writer_count": 19,
        "inflight_mutations": 0,
        "shared_lock_acquired": True,
    }


def test_dormant_builder_is_default_off_and_does_not_call_bridge() -> None:
    boundary = boundary_v2.build_dormant_authenticated_persistent_authority_boundary_v2(
        startup_bridge=lambda _permit: (_ for _ in ()).throw(
            AssertionError("bridge must remain dormant")
        )
    )

    snapshot = boundary.snapshot()
    result = boundary(_permit())

    assert snapshot["default_off"] is True
    assert snapshot["temporary_offline_ready"] is False
    assert result["ok"] is False
    assert result["reason"] == "AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_DEFAULT_OFF"
    assert result["filesystem_accessed"] is False
    assert result["real_registry_accessed"] is False
    assert result["no_order_sent"] is True
    assert result["live_allowed"] is False


def test_authenticated_persistent_authority_boundary_harness_passes() -> None:
    result = harness_v2.run_authenticated_persistent_authority_boundary_harness_v2()

    assert result["ok"] is True
    assert result["temporary_storage_removed"] is True
    assert result["persistent_root_read"] is True
    assert result["persistent_revocation_checked"] is True
    assert result["multistore_recovery_verified"] is True
    assert result["real_registry_accessed"] is False
    assert result["network_accessed"] is False
    assert result["no_order_sent"] is True
    assert result["production_ready"] is False
    assert result["live_allowed"] is False


def test_revoked_persistent_root_blocks_before_multistore_and_bridge() -> None:
    with tempfile.TemporaryDirectory(prefix="c3_boundary_revoked_v2_") as root:
        values = harness_v2.build_authenticated_persistent_authority_boundary_context_v2(
            Path(root), revoked=True
        )

        result = values["boundary"](_permit())

        assert result["ok"] is False
        assert result["reason"] == "PERSISTENT_ROOT_AUTHORITY_REVOKED"
        assert result["root_signature_verified"] is True
        assert result["root_revocation_checked"] is True
        assert result["root_revoked"] is True
        assert values["root_provider"].call_count == 1
        assert values["revocation"].call_count == 1
        assert values["multistore"].call_count == 0
        assert values["prepared"].call_count == 0


def test_tampered_multistore_receipt_fails_closed_before_bridge() -> None:
    with tempfile.TemporaryDirectory(prefix="c3_boundary_tamper_v2_") as root:
        values = harness_v2.build_authenticated_persistent_authority_boundary_context_v2(
            Path(root)
        )
        original = values["multistore"].recover_multistore_v2

        def tampered(**kwargs):
            receipt = original(**kwargs)
            receipt["prepared_transactions_remaining"] = 1
            return receipt

        values["multistore"].recover_multistore_v2 = tampered

        result = values["boundary"](_permit())

        assert result["ok"] is False
        assert result["reason"] == "PERSISTENT_MULTISTORE_RECOVERY_RECEIPT_INVALID"
        assert values["multistore"].call_count == 1
        assert values["prepared"].call_count == 0
        assert result["live_allowed"] is False


def test_invalid_maintenance_permit_blocks_before_filesystem_access() -> None:
    with tempfile.TemporaryDirectory(prefix="c3_boundary_permit_v2_") as root:
        values = harness_v2.build_authenticated_persistent_authority_boundary_context_v2(
            Path(root)
        )
        permit = _permit()
        permit["registered_writer_count"] = 18

        result = values["boundary"](permit)

        assert result["ok"] is False
        assert result["reason"] == "AUTHENTICATED_PERSISTENT_AUTHORITY_PERMIT_INVALID"
        assert values["root_provider"].call_count == 0
        assert values["revocation"].call_count == 0
        assert values["multistore"].call_count == 0
        assert values["prepared"].call_count == 0
        assert result["filesystem_accessed"] is False
