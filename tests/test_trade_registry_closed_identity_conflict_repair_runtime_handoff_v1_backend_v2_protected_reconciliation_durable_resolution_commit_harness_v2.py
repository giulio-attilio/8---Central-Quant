import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_commit_contract_v2 as commit_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_commit_harness_v2 as harness_v2


def test_durable_resolution_commit_harness_passes():
    result = harness_v2.run_durable_resolution_commit_harness_v2()
    assert result["ok"] is True, result
    assert result["passed_count"] == result["check_count"] == 12


def test_durable_resolution_commit_receipt_is_protected_and_valid():
    result = harness_v2.run_durable_resolution_commit_harness_v2()
    receipt = result["protected_receipt"]
    assert commit_v2.protected_durable_resolution_commit_receipt_valid_v2(receipt)
    assert repr(receipt) == "ProtectedDurableResolutionCommitReceiptV2(<protected>)"
    assert receipt.receipt["resolution_state"] == "RESOLVED"
    assert receipt.receipt["consumption_count"] == 1


def test_durable_resolution_commit_has_no_operational_access():
    result = harness_v2.run_durable_resolution_commit_harness_v2()
    assert result["temporary_filesystem_accessed"] is True
    assert result["temporary_storage_removed"] is True
    assert result["resolver_called"] is False
    assert result["barrier_called"] is False
    assert result["backend_called"] is False
    assert result["real_registry_accessed"] is False
    assert result["network_accessed"] is False
    assert result["broker_called"] is False
    assert result["no_order_sent"] is True
