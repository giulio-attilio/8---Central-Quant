import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_outcome_envelope_contract_v2 as envelope_v2


def test_resolution_outcome_envelope_is_default_off():
    result = envelope_v2.DormantResolutionOutcomeEnvelopeContractV2().issue_offline(None)
    assert result["ok"] is False
    assert result["reason"] == "RESOLUTION_OUTCOME_ENVELOPE_V2_DEFAULT_OFF"
    assert result["write_executed"] is False


def test_resolution_outcome_envelope_rejects_unknown_source_kind_first():
    contract = envelope_v2.DormantResolutionOutcomeEnvelopeContractV2(
        envelope_v2.DormantResolutionOutcomeEnvelopeConfigV2(
            enabled=True,
            scope_attestation=envelope_v2.OFFLINE_RESOLUTION_OUTCOME_ENVELOPE_SCOPE_ATTESTATION_V2,
            expected_source_kind="UNKNOWN",
        )
    )
    result = contract.issue_offline(None)
    assert result["reason"] == "RESOLUTION_OUTCOME_SOURCE_KIND_INVALID"
