"""Synthetic regression: validate each store binding before the next call."""
import tempfile
from dataclasses import asdict
from pathlib import Path

import pytest
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2 as adapters
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_harness_v2 as harness


@pytest.fixture
def values():
    with tempfile.TemporaryDirectory(prefix="c3_cross_binding_order_") as root:
        result = harness.build_authenticated_persistent_authority_production_adapters_context_v2(Path(root))
        with result["maintenance_coordinator"].maintenance_lease() as issued:
            result["permit"] = asdict(issued)
            yield result


def permit(values):
    return dict(values["permit"])


@pytest.mark.parametrize("role", ["transaction_port", "resolved_port"])
@pytest.mark.parametrize("field", ["maintenance_epoch", "lock_namespace_sha256",
    "root_authority_attestation_sha256", "storage_binding_sha256"])
def test_cross_bound_receipt_stops_before_next_stage(values, monkeypatch, role, field):
    port = values[role]
    original = port.recover_store_v2

    def wrong_binding(**kwargs):
        receipt = original(**kwargs)
        receipt[field] = "a" * 64 if receipt[field] != "a" * 64 else "b" * 64
        # Recompute integrity: the defect is cross-binding, not a damaged hash.
        receipt["receipt_sha256"] = adapters.store_recovery_port_receipt_sha256_v2(receipt)
        return receipt

    monkeypatch.setattr(port, "recover_store_v2", wrong_binding)
    result = values["boundary"](permit(values))
    assert result["ok"] is False
    assert result["reason"] == "PERSISTENT_MULTISTORE_RECOVERY_FAILED_CLOSED"
    assert values["transaction_port"].call_count == 1
    assert values["resolved_port"].call_count == (0 if role == "transaction_port" else 1)
    assert values["prepared"].call_count == 0
    assert result["production_authority"] is False
    assert result["live_allowed"] is False


def test_clean_sequence_still_recovers_both_stores_then_bridge(values):
    result = values["boundary"](permit(values))
    assert result["ok"] is True, result.get("reason")
    assert values["transaction_port"].call_count == 1
    assert values["resolved_port"].call_count == 1
    assert values["prepared"].call_count == 1
    assert result["production_authority"] is False
    assert result["runtime_integrated"] is False


def test_disabled_coordinator_does_not_call_injected_stores(values):
    dormant = adapters.CoordinatedMultistoreStartupRecoveryV2(
        transaction_recovery=values["transaction_port"], resolved_recovery=values["resolved_port"])
    with pytest.raises(RuntimeError, match="COORDINATED_MULTISTORE_RECOVERY_NOT_READY"):
        dormant.recover_multistore_v2(maintenance_permit=permit(values),
            root_authority_attestation=values["attestation"], now_epoch=1500)
    assert values["transaction_port"].call_count == 0
    assert values["resolved_port"].call_count == 0
