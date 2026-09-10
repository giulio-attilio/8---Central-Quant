import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_restart_admission_contract_v2 as admission_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_restart_admission_harness_v2 as harness_v2


def test_durable_restart_admission_harness_passes_all_checks():
    result = harness_v2.run_durable_restart_admission_harness_v2()
    assert result["ok"] is True, result
    assert result["passed_count"] == result["check_count"] == 12
    assert all(item["passed"] is True for item in result["checks"])


def test_durable_restart_admission_is_protected_and_non_executable():
    result = harness_v2.run_durable_restart_admission_harness_v2()
    protected = result["protected_admission"]
    assert admission_v2.protected_durable_restart_admission_valid_v2(protected)
    assert repr(protected) == "ProtectedDurableRestartAdmissionV2(<protected>)"
    assert protected.admission["barrier_call_allowed"] is False
    assert protected.admission["resolver_call_allowed"] is False
    assert protected.admission["resolution_authority_granted"] is False


def test_durable_restart_admission_harness_has_no_operational_side_effects():
    result = harness_v2.run_durable_restart_admission_harness_v2()
    assert result["temporary_filesystem_accessed"] is True
    assert result["temporary_write_executed"] is True
    assert result["temporary_storage_removed"] is True
    assert result["real_registry_accessed"] is False
    assert result["network_accessed"] is False
    assert result["broker_called"] is False
    assert result["no_order_sent"] is True
