import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_preparation_contract_v2 as preparation_v2


def test_durable_resolution_preparation_is_default_off():
    result = preparation_v2.DormantDurableResolutionPreparationContractV2().prepare_offline(
        None, None, now_epoch=0
    )
    assert result["ok"] is False
    assert result["reason"] == "DURABLE_RESOLUTION_PREPARATION_V2_DEFAULT_OFF"
    assert result["temporary_filesystem_accessed"] is False
    assert result["write_executed"] is False
    assert result["resolver_called"] is False


def test_durable_resolution_preparation_requires_all_hash_pins():
    contract = preparation_v2.DormantDurableResolutionPreparationContractV2(
        preparation_v2.DormantDurableResolutionPreparationConfigV2(
            enabled=True,
            scope_attestation=preparation_v2.OFFLINE_DURABLE_RESOLUTION_PREPARATION_SCOPE_ATTESTATION_V2,
        )
    )
    result = contract.prepare_offline(None, None, now_epoch=0)
    assert result["ok"] is False
    assert result["reason"] == "DURABLE_RESOLUTION_PREPARATION_PINS_INVALID"
