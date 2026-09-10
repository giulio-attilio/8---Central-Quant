import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_preparation_contract_v2 as preparation_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_preparation_harness_v2 as harness_v2


def test_durable_resolution_preparation_harness_passes():
    result = harness_v2.run_durable_resolution_preparation_harness_v2()
    assert result["ok"] is True, result
    assert result["passed_count"] == result["check_count"] == 11


def test_preparation_is_protected_and_non_executable():
    result = harness_v2.run_durable_resolution_preparation_harness_v2()
    protected = result["protected_preparation"]
    assert preparation_v2.protected_durable_resolution_preparation_valid_v2(protected)
    assert repr(protected) == "ProtectedDurableResolutionPreparationV2(<protected>)"
    assert protected.preparation["resolver_call_allowed"] is False
    assert protected.preparation["durable_authority_consumed"] is False
    assert protected.preparation["resolution_executed"] is False


def test_preparation_harness_has_only_temporary_storage_side_effects():
    result = harness_v2.run_durable_resolution_preparation_harness_v2()
    assert result["temporary_filesystem_accessed"] is True
    assert result["temporary_write_executed"] is True
    assert result["temporary_storage_removed"] is True
    assert result["real_registry_accessed"] is False
    assert result["network_accessed"] is False
    assert result["broker_called"] is False
    assert result["no_order_sent"] is True
