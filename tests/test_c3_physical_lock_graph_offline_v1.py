"""Synthetic-only lock graph inspection; never import or execute main.py."""

from dataclasses import replace
from pathlib import Path
import tempfile

import pytest

import trade_registry_c3_physical_lock_graph_offline_v1 as graph_v1
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as wal_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_v2 as boundary_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_harness_v2 as reference
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2 as multistore_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_locked_aggregate_collection_offline_harness_v2 as collection_harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_multistore_observation_lease_offline_harness_v2 as observation_harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_multistore_observation_lease_offline_v2 as observation_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_bridge_v2 as bridge_v2
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_v1
import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as storage_v1


@pytest.fixture
def temporary_graph():
    with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as root:
        root_path = Path(root)
        base = reference.build_authenticated_persistent_authority_production_adapters_context_v2(root_path)
        wal = wal_v2.TemporaryPhysicalDurableRawTransactionBackendV2(
            root_path, enabled=True,
            scope_attestation=wal_v2.TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2,
            clock=base["boundary"]._clock,
        )
        wal._store.initialize_synthetic_registry({"open_trades": {}, "closed_trades": []})
        ledger = base["bridge"]._physical_store._ledger
        lock_backend = wal._lock_backend
        coordinator = coordinator_v1.ClosedRepairWriterRuntimeCoordinatorV1(
            config=coordinator_v1.WriterRuntimeCoordinatorConfigV1(
                enabled=True, maintenance_only=True,
            ),
            lock_backend=lock_backend,
            lease_store=storage_v1.DurableJsonMaintenanceLeaseStoreV1(
                lock_backend.storage_root, enabled=True,
            ),
            clock=lambda: float(base["boundary"]._clock()),
            nonce_source=lambda: "synthetic-lock-graph",
        )
        coordinator.register_all_declared_writers()
        transaction_port = reference.TemporaryStoreRecoveryPortV2(
            root_path / "graph_transaction_state.json", "TRANSACTION_STORE",
            base["attestation"]["storage_binding_sha256"],
            lock_backend=lock_backend, lock_namespace_sha256=base["lock_namespaces"][0],
        )
        resolved_port = reference.TemporaryStoreRecoveryPortV2(
            root_path / "graph_resolved_state.json", "RESOLVED_AUTHORITY_STORE",
            base["attestation"]["storage_binding_sha256"],
            lock_backend=lock_backend, lock_namespace_sha256=base["lock_namespaces"][1],
        )
        multistore = multistore_v2.CoordinatedMultistoreStartupRecoveryV2(
            replace(
                base["multistore"]._config,
                expected_transaction_recovery_object_identity_sha256=reference._object_identity(transaction_port),
                expected_resolved_recovery_object_identity_sha256=reference._object_identity(resolved_port),
                expected_lock_backend_object_identity_sha256=reference._object_identity(lock_backend),
                expected_lock_storage_root_binding_sha256=(
                    multistore_v2.authority_adapter_storage_root_binding_sha256_v2(lock_backend.storage_root)
                ),
                expected_maintenance_coordinator_object_identity_sha256=reference._object_identity(coordinator),
            ),
            transaction_recovery=transaction_port,
            resolved_recovery=resolved_port,
            lock_backend=lock_backend,
            maintenance_coordinator=coordinator,
        )
        bridge = bridge_v2.ResolvedAuthorityStartupRecoveryBridgeV2(
            replace(
                base["bridge"]._config,
                expected_maintenance_coordinator_object_identity_sha256=reference._object_identity(coordinator),
                expected_lock_backend_object_identity_sha256=reference._object_identity(lock_backend),
            ),
            prepared_recovery=base["bridge"]._prepared_recovery,
            physical_store=base["bridge"]._physical_store,
            clock=base["bridge"]._clock,
            maintenance_coordinator=coordinator,
            lock_backend=lock_backend,
        )
        observation = observation_harness.make_physical_multistore_observation_lease_v2(
            backend=wal, ledger=ledger, clock=base["boundary"]._clock,
        )
        collector = collection_harness.make_physical_locked_aggregate_collection_v2(
            observation_lease=observation, backend=wal, ledger=ledger,
            clock=base["boundary"]._clock,
        )
        boundary = boundary_v2.AuthenticatedPersistentAuthorityBoundaryV2(
            replace(
                base["boundary"]._config,
                expected_multistore_recovery_object_identity_sha256=reference._object_identity(multistore),
                expected_startup_bridge_object_identity_sha256=reference._object_identity(bridge),
                require_locked_physical_aggregate=True,
                expected_locked_physical_aggregate_collector_object_identity_sha256=reference._object_identity(collector),
            ),
            root_state_provider=base["root_provider"],
            root_authority_verifier=base["verifier"],
            root_revocation_source=base["revocation"],
            multistore_recovery=multistore,
            startup_bridge=bridge,
            locked_physical_aggregate_collector=collector,
            clock=base["boundary"]._clock,
        )
        yield dict(
            coordinator=coordinator, wal_backend=wal, resolved_ledger=ledger,
            observation_lease=observation, aggregate_collector=collector,
            multistore_recovery=multistore, startup_bridge=bridge,
            authority_boundary=boundary,
        )


def inspect(values, *, enabled=True):
    return graph_v1.inspect_c3_physical_lock_graph_offline_v1(enabled=enabled, **values)


def test_default_off_does_not_inspect_dependencies():
    result = graph_v1.inspect_c3_physical_lock_graph_offline_v1()
    assert result["reason"] == "C3_PHYSICAL_LOCK_GRAPH_DEFAULT_OFF"
    assert result["structural_binding_verified"] is False
    assert result["production_ready"] is False


def test_colocated_temporary_graph_is_structural_only(temporary_graph):
    result = inspect(temporary_graph)
    assert result["ok"] is True, result["reason"]
    assert result["structural_binding_verified"] is True
    assert result["synthetic_registry_lock_lease_colocated"] is True
    assert result["physical_lock_acquired"] is False
    assert result["writer_runtime_lock_verified"] is False
    assert result["store_recovery_ports_verified"] is False
    assert result["registry_or_wal_contents_read"] is False
    assert result["production_ready"] is False
    assert result["runtime_integrated"] is False
    assert result["live_allowed"] is False


def test_same_outer_lock_blocks_nested_wal_observation_during_maintenance(temporary_graph):
    assert inspect(temporary_graph)["structural_binding_verified"] is True
    coordinator = temporary_graph["coordinator"]
    wal = temporary_graph["wal_backend"]
    observation = temporary_graph["observation_lease"]
    with coordinator.maintenance_lease():
        assert wal.mark_lock_probe_offline() is False
        with pytest.raises(
            observation_v2.TemporaryPhysicalObservationLeaseBlockedV2,
            match="PHYSICAL_MULTISTORE_OBSERVATION_LOCK_TIMEOUT",
        ):
            with observation.hold_offline(expires_at_epoch=observation._clock() + 60):
                pytest.fail("nested observation must not acquire the writer lock")
    assert wal.mark_lock_probe_offline() is True


def test_mismatched_writer_lock_backend_fails_closed(temporary_graph, monkeypatch):
    monkeypatch.setattr(temporary_graph["multistore_recovery"], "_lock_backend", object())
    result = inspect(temporary_graph)
    assert result["reason"] == "C3_PHYSICAL_LOCK_GRAPH_WRITER_WAL_DOMAIN_MISMATCH"
    assert result["ok"] is False


def test_mismatched_recovery_port_lock_fails_closed(temporary_graph, monkeypatch):
    monkeypatch.setattr(
        temporary_graph["multistore_recovery"]._transaction_recovery,
        "recovery_lock_backend", object(),
    )
    assert inspect(temporary_graph)["reason"] == "C3_PHYSICAL_LOCK_GRAPH_WRITER_WAL_DOMAIN_MISMATCH"


def test_mismatched_collector_or_ledger_fails_closed(temporary_graph, monkeypatch):
    monkeypatch.setattr(temporary_graph["aggregate_collector"], "_ledger", object())
    assert inspect(temporary_graph)["reason"] == "C3_PHYSICAL_LOCK_GRAPH_STORE_INSTANCE_MISMATCH"


def test_registry_outside_lock_domain_fails_closed(temporary_graph, monkeypatch, tmp_path):
    external_synthetic_registry = tmp_path / "synthetic_trade_registry.json"
    external_synthetic_registry.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(temporary_graph["wal_backend"]._store, "_target", external_synthetic_registry)
    result = inspect(temporary_graph)
    assert result["reason"] == "C3_PHYSICAL_LOCK_GRAPH_SYNTHETIC_REGISTRY_DOMAIN_MISMATCH"
    assert result["synthetic_registry_lock_lease_colocated"] is False
    assert result["production_ready"] is False


def test_lock_directory_outside_registry_domain_fails_closed(temporary_graph, monkeypatch, tmp_path):
    moved_lock_root = tmp_path / "other-locks"
    moved_lock_root.mkdir()
    monkeypatch.setattr(temporary_graph["coordinator"]._lock_backend, "_root", moved_lock_root)
    monkeypatch.setattr(temporary_graph["coordinator"]._lease_store, "_root", moved_lock_root)
    result = inspect(temporary_graph)
    assert result["reason"] == "C3_PHYSICAL_LOCK_GRAPH_SYNTHETIC_REGISTRY_DOMAIN_MISMATCH"
    assert result["synthetic_registry_lock_lease_colocated"] is False
    assert result["production_ready"] is False


def test_aggregate_must_be_required_and_pinned(temporary_graph, monkeypatch):
    boundary = temporary_graph["authority_boundary"]
    monkeypatch.setattr(boundary, "_config", replace(boundary._config, require_locked_physical_aggregate=False))
    assert inspect(temporary_graph)["reason"] == "C3_PHYSICAL_LOCK_GRAPH_BOUNDARY_REQUIREMENT_MISSING"


def test_invalid_enable_type_fails_before_inspection():
    result = graph_v1.inspect_c3_physical_lock_graph_offline_v1(enabled=1)
    assert result["reason"] == "C3_PHYSICAL_LOCK_GRAPH_ENABLE_INVALID"


def test_runtime_remains_unwired():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "trade_registry_c3_physical_lock_graph_offline_v1" not in source
