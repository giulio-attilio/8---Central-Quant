from __future__ import annotations

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_bridge_harness_v2 as harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_bridge_v2 as bridge_v2


def test_bridge_is_default_off_and_no_io() -> None:
    bridge = bridge_v2.build_dormant_resolved_authority_startup_recovery_bridge_v2()
    snapshot = bridge.snapshot()
    result = bridge({})

    assert snapshot["enabled"] is False
    assert snapshot["default_off"] is True
    assert snapshot["temporary_offline_ready"] is False
    assert snapshot["physical_store_implementation_bound"] is False
    assert snapshot["filesystem_accessed"] is False
    assert snapshot["production_ready"] is False
    assert snapshot["runtime_integrated"] is False
    assert snapshot["live_allowed"] is False
    assert result["ok"] is False
    assert result["reason"] == "RESOLVED_AUTHORITY_STARTUP_RECOVERY_BRIDGE_DEFAULT_OFF"
    assert result["filesystem_accessed"] is False
    assert result["no_order_sent"] is True


def test_bridge_harness_composes_prepared_and_resolved_recovery() -> None:
    result = harness_v2.run_resolved_authority_startup_recovery_bridge_harness_v2()

    assert result["ok"] is True
    assert result["prepared_recovery_called_once"] is True
    assert result["physical_store_implementation_bound"] is True
    assert result["temporary_storage_removed"] is True
    assert result["real_registry_accessed"] is False
    assert result["network_accessed"] is False
    assert result["broker_called"] is False
    assert result["no_order_sent"] is True
    assert result["production_ready"] is False
    assert result["runtime_integrated"] is False
    assert result["live_allowed"] is False
