import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_closure_attestation_contract_v2 as closure_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_closure_attestation_harness_v2 as harness_v2


def test_closure_attestation_harness_passes():
    result = harness_v2.run_reconciliation_closure_attestation_harness_v2()
    assert result["ok"] is True, result["reason"]
    assert result["passed_count"] == result["check_count"] == 18


def test_both_closure_attestations_are_protected_and_valid():
    result = harness_v2.run_reconciliation_closure_attestation_harness_v2()
    legacy = result["legacy_attestation"]
    durable = result["durable_attestation"]
    assert closure_v2.protected_reconciliation_closure_attestation_valid_v2(legacy)
    assert closure_v2.protected_reconciliation_closure_attestation_valid_v2(durable)
    assert repr(legacy) == "ProtectedReconciliationClosureAttestationV2(<protected>)"
    assert repr(durable) == "ProtectedReconciliationClosureAttestationV2(<protected>)"


def test_closure_attestation_never_grants_state_mutation_or_retry():
    result = harness_v2.run_reconciliation_closure_attestation_harness_v2()
    for protected in (result["legacy_attestation"], result["durable_attestation"]):
        record = protected.attestation
        assert record["obligation_preserved_immutable"] is True
        assert record["new_apply_allowed"] is False
        assert record["retry_allowed"] is False
        assert record["state_update_allowed"] is False
        assert record["runtime_mutation_allowed"] is False
