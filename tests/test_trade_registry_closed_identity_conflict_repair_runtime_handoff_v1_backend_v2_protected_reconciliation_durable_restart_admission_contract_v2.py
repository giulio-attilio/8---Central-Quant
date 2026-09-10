import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_restart_admission_contract_v2 as admission_v2


def test_durable_restart_admission_is_default_off_before_input_inspection():
    result = admission_v2.DormantDurableRestartAdmissionContractV2().issue_offline(
        None, None, None, now_epoch=0
    )
    assert result["ok"] is False
    assert result["reason"] == "DURABLE_RESTART_ADMISSION_V2_DEFAULT_OFF"
    assert result["temporary_filesystem_accessed"] is False
    assert result["write_executed"] is False


def test_durable_restart_admission_config_rejects_excessive_ttl():
    try:
        admission_v2.DormantDurableRestartAdmissionConfigV2(
            maximum_authority_ttl_seconds=301
        )
    except ValueError as exc:
        assert "maximum_authority_ttl_seconds" in str(exc)
    else:
        raise AssertionError("excessive TTL was accepted")
