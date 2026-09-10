from __future__ import annotations

import tempfile
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_physical_store_reference_harness_v2 as harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_physical_store_reference_v2 as reference_v2


def test_reference_is_default_off_and_no_io() -> None:
    reference = (
        reference_v2.build_dormant_resolved_authority_physical_store_reference_v2()
    )
    snapshot = reference.snapshot()
    result = reference.open_offline(now_epoch=harness_v2.SYNTHETIC_NOW_V2)

    assert snapshot["enabled"] is False
    assert snapshot["default_off"] is True
    assert snapshot["physical_store_implementation_bound"] is False
    assert snapshot["filesystem_accessed"] is False
    assert snapshot["production_ready"] is False
    assert snapshot["runtime_integrated"] is False
    assert snapshot["live_allowed"] is False
    assert result["ok"] is False
    assert result["reason"] == "RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_DEFAULT_OFF"
    assert result["filesystem_accessed"] is False
    assert result["no_order_sent"] is True


def test_temporary_physical_reference_harness_passes() -> None:
    result = harness_v2.run_resolved_authority_physical_store_reference_harness_v2()

    assert result["ok"] is True
    assert result["temporary_storage_removed"] is True
    assert result["physical_store_implementation_bound"] is True
    assert result["real_registry_accessed"] is False
    assert result["network_accessed"] is False
    assert result["broker_called"] is False
    assert result["no_order_sent"] is True
    assert result["production_ready"] is False
    assert result["runtime_integrated"] is False
    assert result["live_allowed"] is False


def test_revoked_root_fails_before_filesystem_access() -> None:
    with tempfile.TemporaryDirectory(prefix="c3_resolved_revoked_v2_") as root:
        root_path = Path(root)
        values = harness_v2.build_resolved_authority_physical_store_reference_context_v2(
            root_path, revoked=True
        )
        result = values["reference"].open_offline(
            now_epoch=harness_v2.SYNTHETIC_NOW_V2
        )

        assert result["ok"] is False
        assert result["reason"] == "RESOLVED_AUTHORITY_ROOT_REVOKED"
        assert result["root_revocation_checked"] is True
        assert result["root_revoked"] is True
        assert result["filesystem_accessed"] is False
        assert not (root_path / "authority.snapshot.json").exists()


def test_non_temporary_storage_is_rejected_without_opening_it() -> None:
    repository_path = Path(__file__).resolve().parents[1]
    values = harness_v2.build_resolved_authority_physical_store_reference_context_v2(
        repository_path
    )
    snapshot = values["reference"].snapshot()

    assert snapshot["ready_for_temporary_offline_use"] is False
    assert snapshot["reason"] == "RESOLVED_AUTHORITY_STORAGE_OUTSIDE_SYSTEM_TEMP"
    assert snapshot["filesystem_accessed"] is False
    assert not (repository_path / "authority.snapshot.json").exists()


def test_receipt_hash_detects_tampering() -> None:
    with tempfile.TemporaryDirectory(prefix="c3_resolved_receipt_v2_") as root:
        values = harness_v2.build_resolved_authority_physical_store_reference_context_v2(
            root
        )
        result = values["reference"].open_offline(
            now_epoch=harness_v2.SYNTHETIC_NOW_V2
        )
        receipt = {
            key: item
            for key, item in result.items()
            if key
            not in {
                "ok",
                "status",
                "reason",
                "observed",
            }
        }

        assert result["ok"] is True
        assert result["receipt_sha256"] == (
            reference_v2.resolved_authority_physical_store_reference_receipt_sha256_v2(
                receipt
            )
        )
        receipt["record_count"] = 1
        assert result["receipt_sha256"] != (
            reference_v2.resolved_authority_physical_store_reference_receipt_sha256_v2(
                receipt
            )
        )
