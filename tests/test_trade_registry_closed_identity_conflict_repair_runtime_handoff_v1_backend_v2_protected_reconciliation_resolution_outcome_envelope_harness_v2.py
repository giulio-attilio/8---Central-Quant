import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_outcome_envelope_contract_v2 as envelope_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_outcome_envelope_harness_v2 as harness_v2


def test_resolution_outcome_envelope_harness_passes():
    result = harness_v2.run_resolution_outcome_envelope_harness_v2()
    assert result["ok"] is True, result["reason"]
    assert result["passed_count"] == result["check_count"] == 11


def test_both_native_envelopes_are_protected_and_valid():
    result = harness_v2.run_resolution_outcome_envelope_harness_v2()
    legacy = result["legacy_envelope"]
    durable = result["durable_envelope"]
    assert envelope_v2.protected_resolution_outcome_envelope_valid_v2(legacy)
    assert envelope_v2.protected_resolution_outcome_envelope_valid_v2(durable)
    assert repr(legacy) == "ProtectedResolutionOutcomeEnvelopeV2(<protected>)"
    assert repr(durable) == "ProtectedResolutionOutcomeEnvelopeV2(<protected>)"


def test_envelopes_preserve_source_semantics_without_conversion():
    result = harness_v2.run_resolution_outcome_envelope_harness_v2()
    legacy = result["legacy_envelope"].envelope
    durable = result["durable_envelope"].envelope
    assert legacy["source_kind"] == envelope_v2.ORIGINAL_SESSION_RECEIPT_SOURCE_V2
    assert durable["source_kind"] == envelope_v2.DURABLE_RESTART_RECEIPT_SOURCE_V2
    assert legacy["conversion_performed"] is False
    assert durable["conversion_performed"] is False
    assert durable["restart_reconstructible"] is True
