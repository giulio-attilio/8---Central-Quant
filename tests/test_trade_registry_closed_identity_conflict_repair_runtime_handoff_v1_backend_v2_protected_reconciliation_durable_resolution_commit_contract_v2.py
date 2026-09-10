import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_commit_contract_v2 as commit_v2


def test_durable_resolution_commit_is_default_off():
    result = commit_v2.DormantDurableResolutionCommitContractV2().commit_offline(
        None, now_epoch=0
    )
    assert result["ok"] is False
    assert result["reason"] == "DURABLE_RESOLUTION_COMMIT_V2_DEFAULT_OFF"
    assert result["filesystem_accessed"] is False
    assert result["write_executed"] is False


def test_durable_resolution_commit_requires_all_pins():
    contract = commit_v2.DormantDurableResolutionCommitContractV2(
        commit_v2.DormantDurableResolutionCommitConfigV2(
            enabled=True,
            scope_attestation=commit_v2.OFFLINE_DURABLE_RESOLUTION_COMMIT_SCOPE_ATTESTATION_V2,
        )
    )
    result = contract.commit_offline(None, now_epoch=0)
    assert result["ok"] is False
    assert result["reason"] == "DURABLE_RESOLUTION_COMMIT_PINS_INVALID"
