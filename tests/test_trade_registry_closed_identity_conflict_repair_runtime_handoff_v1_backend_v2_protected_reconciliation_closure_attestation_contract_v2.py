import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_closure_attestation_contract_v2 as closure_v2


def test_closure_attestation_is_default_off():
    result = closure_v2.DormantReconciliationClosureAttestationContractV2().issue_offline(None, None)
    assert result["ok"] is False
    assert result["reason"] == "RECONCILIATION_CLOSURE_ATTESTATION_V2_DEFAULT_OFF"
    assert result["write_executed"] is False


def test_closure_attestation_requires_all_pins():
    contract = closure_v2.DormantReconciliationClosureAttestationContractV2(
        closure_v2.DormantReconciliationClosureAttestationConfigV2(
            enabled=True,
            scope_attestation=closure_v2.OFFLINE_RECONCILIATION_CLOSURE_ATTESTATION_SCOPE_V2,
        )
    )
    result = contract.issue_offline(None, None)
    assert result["reason"] == "RECONCILIATION_CLOSURE_ATTESTATION_PINS_INVALID"
