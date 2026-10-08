"""Synthetic recovery transport/denial, not production startup or restart proof."""
import copy
import json
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

import pytest
import c3_runtime_dependency_assembly_offline_v1 as assembly
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as wal_contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_harness_v2 as wal_request_harness
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as physical_wal
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_startup_recovery_harness_v2 as wal_recovery_harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_harness_v2 as reference
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_v2 as boundary_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_harness_v2 as physical_reference
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2 as adapters_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_multistore_observation_lease_offline_harness_v2 as observation_lease_harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_multistore_observation_lease_offline_v2 as observation_lease_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_locked_aggregate_collection_offline_harness_v2 as aggregate_collection_harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_physical_store_reference_v2 as resolved_reference
from tests.test_c3_runtime_dependency_assembly_offline_v1 import fixture


@pytest.fixture
def synthetic_root():
    # The existing physical-store contract requires the OS temporary root, not
    # pytest's /scratch tree. Keep that containment rule unchanged.
    with tempfile.TemporaryDirectory(prefix="c3_evidence_transport_") as root:
        yield Path(root)


class ReceiptPort:
    def __init__(self):
        self.value = None
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return copy.deepcopy(self.value)

    def __repr__(self):
        return "<ReceiptPort synthetic protected>"


def context(root, *, revoked=False):
    values = reference.build_authenticated_persistent_authority_boundary_context_v2(root, revoked=revoked)
    boundary = values["boundary"]
    d, traps = fixture()
    port = ReceiptPort()
    d = replace(d, ports=replace(d.ports, startup_state=port),
        root_state_provider=values["root_provider"], root_authority_verifier=boundary._root_verifier,
        root_revocation_source=values["revocation"], multistore_recovery=values["multistore"],
        startup_bridge=values["bridge"], clock=boundary._clock)
    graph = assembly.assemble_c3_dependencies_offline_v1(d)
    permit = {
        "maintenance_epoch": reference.hash_v2.stable_sha256_v2({"epoch": "synthetic"}),
        "lock_namespace_sha256": reference.hash_v2.stable_sha256_v2({"namespace": "synthetic"}),
        "state": "QUIESCED", "registered_writer_count": 19,
        "inflight_mutations": 0, "shared_lock_acquired": True,
    }
    return values, graph, port, permit, traps


def counts(values):
    return tuple(values[name].call_count for name in
                 ("root_provider", "revocation", "multistore", "prepared"))


def assert_cannot_start(graph, port, receipt):
    port.value = copy.deepcopy(receipt)
    # Explicit diagnostic transport. This is NOT production startup-state schema
    # conversion, authentication, or a forged production verifier.
    transported = port()
    assert transported == receipt and transported is not receipt
    calls = port.calls
    assert graph.snapshot()["ok"] is True
    assert graph.snapshot()["production_ready"] is False
    with pytest.raises(assembly.gate_v1.RuntimeStartupAdmissionBlocked):
        with graph.gate.startup_admission(transported):
            pytest.fail("synthetic evidence admitted startup")
    with pytest.raises(assembly.composition_v1.RuntimeProductionStartupCompositionBlocked):
        graph.composition.rehearse_offline()
    with pytest.raises(assembly.coordinator_v1.WriterRuntimeCoordinationBlocked):
        graph.interlock.run_startup_recovery_v1()
    assert port.calls == calls  # Disabled composition never consumes this source.


def test_successful_reference_receipt_does_not_enable_dormant_graph(synthetic_root):
    values, graph, port, permit, traps = context(synthetic_root)
    assert counts(values) == (0, 0, 0, 0)
    assert graph.authority(permit)["ok"] is False
    assert counts(values) == (0, 0, 0, 0)
    receipt = values["boundary"](permit)
    assert receipt["ok"] is True, receipt.get("reason")
    assert counts(values) == (1, 1, 1, 1)
    assert receipt["startup_recovery_attestation_sha256"] == (
        assembly.seam_v1.startup_recovery_attestation_sha256_v1(receipt))
    for flag in ("production_authority", "production_ready", "runtime_integrated", "live_allowed"):
        assert receipt[flag] is False
    assert_cannot_start(graph, port, receipt)
    assert counts(values) == (1, 1, 1, 1)
    assert all(trap.calls == 0 for trap in traps)


@pytest.mark.parametrize("changes", [
    {"shared_lock_acquired": False}, {"registered_writer_count": 18},
    {"inflight_mutations": 1}, {"state": "ACTIVE"},
])
def test_invalid_permit_is_rejected_before_persistent_reads(synthetic_root, changes):
    values, graph, port, permit, traps = context(synthetic_root)
    receipt = values["boundary"](dict(permit, **changes))
    assert receipt["ok"] is False and counts(values) == (0, 0, 0, 0)
    assert receipt["reason"] == "AUTHENTICATED_PERSISTENT_AUTHORITY_PERMIT_INVALID"
    assert_cannot_start(graph, port, receipt)
    assert counts(values) == (0, 0, 0, 0)
    assert all(trap.calls == 0 for trap in traps)


def test_revoked_root_stops_before_recovery_and_cannot_admit_startup(synthetic_root):
    values, graph, port, permit, traps = context(synthetic_root, revoked=True)
    receipt = values["boundary"](permit)
    assert receipt["ok"] is False and receipt["root_revoked"] is True, receipt.get("reason")
    assert counts(values) == (1, 1, 0, 0)
    assert_cannot_start(graph, port, receipt)
    assert counts(values) == (1, 1, 0, 0)
    assert all(trap.calls == 0 for trap in traps)


def test_recreated_provider_cannot_reuse_old_process_identity_pins(synthetic_root):
    values, graph, port, permit, traps = context(synthetic_root)
    original = values["boundary"]
    # New object over the same temporary fixture, without rewriting its files.
    # This models object reconstruction, not a cross-process restart.
    recreated = copy.copy(values["root_provider"])
    kwargs = dict(root_state_provider=recreated, root_authority_verifier=original._root_verifier,
        root_revocation_source=original._revocation_source,
        multistore_recovery=original._multistore_recovery,
        startup_bridge=original._startup_bridge, clock=original._clock)
    stale = assembly.authority_v2.AuthenticatedPersistentAuthorityBoundaryV2(config=original._config, **kwargs)
    denied = stale(permit)
    assert denied["ok"] is False
    assert stale.snapshot()["reason"].endswith("INSTANCE_MISMATCH")
    assert recreated.call_count == 0 and counts(values) == (0, 0, 0, 0)
    assert_cannot_start(graph, port, denied)
    rebound = assembly.authority_v2.AuthenticatedPersistentAuthorityBoundaryV2(
        config=replace(original._config,
            expected_root_state_provider_object_identity_sha256=reference._object_identity(recreated)), **kwargs)
    recovered = rebound(permit)
    assert recovered["ok"] is True, recovered.get("reason")
    assert recovered["production_authority"] is False
    assert_cannot_start(graph, port, recovered)
    assert graph.authority._config.enabled is False
    assert all(trap.calls == 0 for trap in traps)


@pytest.mark.parametrize("field,value", [
    ("production_authority", True), ("prepared_transactions_after", 1),
    ("maintenance_epoch", "0" * 64),
])
def test_tampered_reference_receipt_is_not_an_activation_permit(synthetic_root, field, value):
    values, graph, port, permit, traps = context(synthetic_root)
    receipt = values["boundary"](permit)
    assert receipt["ok"] is True, receipt.get("reason")
    receipt[field] = value
    assert receipt["startup_recovery_attestation_sha256"] != (
        assembly.seam_v1.startup_recovery_attestation_sha256_v1(receipt))
    assert_cannot_start(graph, port, receipt)
    assert all(trap.calls == 0 for trap in traps)


def test_storage_outside_os_temporary_root_is_still_rejected(tmp_path):
    # /scratch here is synthetic and isolated, but deliberately outside /tmp.
    assert not tmp_path.is_relative_to(Path(tempfile.gettempdir()))
    values, graph, port, permit, traps = context(tmp_path)
    physical = values["bridge"]._physical_store.snapshot()
    assert physical["reason"] == "RESOLVED_AUTHORITY_STORAGE_OUTSIDE_SYSTEM_TEMP"
    receipt = values["boundary"](permit)
    assert receipt["ok"] is False
    assert receipt["reason"] == "AUTHENTICATED_PERSISTENT_AUTHORITY_BRIDGE_CROSS_BINDING_INVALID"
    assert counts(values) == (0, 0, 0, 0)
    assert_cannot_start(graph, port, receipt)
    assert all(trap.calls == 0 for trap in traps)


def physical_context(root):
    """Join the existing physical-lease fixture to the dormant startup graph."""
    values = physical_reference.build_authenticated_persistent_authority_production_adapters_context_v2(root)
    d, traps = fixture()
    port = ReceiptPort()
    d = replace(d, ports=replace(d.ports, startup_state=port),
        root_state_provider=values["root_provider"], root_authority_verifier=values["verifier"],
        root_revocation_source=values["revocation"], multistore_recovery=values["multistore"],
        startup_bridge=values["bridge"], clock=values["boundary"]._clock)
    return values, assembly.assemble_c3_dependencies_offline_v1(d), port, traps


def test_existing_two_store_observation_lease_rejects_separate_lab_roots(synthetic_root):
    # The current integration fixture has separate WAL and RESOLVED roots.
    # The existing aggregate auditor requires both under the WAL root.
    with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as wal_root:
        backend = physical_wal.TemporaryPhysicalDurableRawTransactionBackendV2(
            wal_root, enabled=True,
            scope_attestation=physical_wal.TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2,
            clock=lambda: wal_recovery_harness.SYNTHETIC_NOW_V2,
        )
        values = physical_reference.build_authenticated_persistent_authority_production_adapters_context_v2(
            synthetic_root)
        ledger = values["bridge"]._physical_store._ledger
        lease = observation_lease_harness.make_physical_multistore_observation_lease_v2(
            backend=backend, ledger=ledger, clock=values["boundary"]._clock)
        with pytest.raises(observation_lease_v2.TemporaryPhysicalObservationLeaseBlockedV2) as blocked:
            with lease.hold_offline(expires_at_epoch=values["boundary"]._clock() + 60):
                pytest.fail("separate physical roots must not share an observation lease")
        assert blocked.value.reason == "PHYSICAL_MULTISTORE_OBSERVATION_STORAGE_ROOT_MISMATCH"
        assert lease.snapshot()["held_lock_count"] == 0
        assert values["transaction_port"].call_count == 0
        assert values["resolved_port"].call_count == 0


def test_required_locked_aggregate_without_collector_fails_before_reads(synthetic_root):
    values, graph, port, traps = physical_context(synthetic_root)
    original = values["boundary"]
    boundary = boundary_v2.AuthenticatedPersistentAuthorityBoundaryV2(
        replace(original._config,
            require_locked_physical_aggregate=True,
            expected_locked_physical_aggregate_collector_object_identity_sha256="0" * 64),
        root_state_provider=values["root_provider"],
        root_authority_verifier=values["verifier"],
        root_revocation_source=values["revocation"],
        multistore_recovery=values["multistore"],
        startup_bridge=values["bridge"],
        clock=original._clock,
    )
    receipt = boundary({})
    assert receipt["ok"] is False
    assert receipt["reason"] == "AUTHENTICATED_PERSISTENT_AUTHORITY_AGGREGATE_DEPENDENCY_INVALID"
    assert values["transaction_port"].call_count == 0
    assert values["resolved_port"].call_count == 0
    assert_cannot_start(graph, port, receipt)
    assert all(trap.calls == 0 for trap in traps)


def test_guarded_resolved_bridge_requires_current_lease_and_free_store_lock(synthetic_root):
    values, graph, port, traps = physical_context(synthetic_root)
    guarded = values["bridge"]
    coordinator, backend = values["maintenance_coordinator"], values["lock_backend"]
    assert guarded.snapshot()["temporary_offline_ready"] is True
    with coordinator.maintenance_lease() as issued:
        permit = asdict(issued)
        held = backend.acquire(values["lock_namespaces"][1], 0.02)
        assert held is not None
        try:
            blocked = guarded(permit)
            assert blocked["reason"] == "RESOLVED_AUTHORITY_PHYSICAL_RECOVERY_FAILED_CLOSED"
            assert blocked["ok"] is False
        finally:
            held.release()
        receipt = guarded(permit)
        assert receipt["ok"] is True, receipt.get("reason")
        assert receipt["production_ready"] is False
        assert_cannot_start(graph, port, receipt)
    stale = guarded(permit)
    assert stale["reason"] == "RESOLVED_AUTHORITY_MAINTENANCE_NOT_CURRENT"
    assert stale["ok"] is False
    assert all(trap.calls == 0 for trap in traps)


def test_coordinated_boundary_rejects_unguarded_resolved_bridge_before_reads(synthetic_root):
    values, graph, port, traps = physical_context(synthetic_root)
    unguarded = copy.copy(values["bridge"])
    unguarded._config = replace(unguarded._config, require_coordinated_physical_recovery=False)
    boundary = copy.copy(values["boundary"])
    boundary._startup_bridge = unguarded
    boundary._config = replace(boundary._config,
        expected_startup_bridge_object_identity_sha256=physical_reference._object_identity(unguarded))
    denied = boundary.snapshot()
    assert denied["reason"] == "AUTHENTICATED_PERSISTENT_AUTHORITY_COORDINATED_BRIDGE_MISMATCH"
    assert values["transaction_port"].call_count == 0
    assert_cannot_start(graph, port, boundary({}))
    assert all(trap.calls == 0 for trap in traps)


def test_physical_maintenance_receipt_stays_dormant_after_lease_release(synthetic_root):
    values, graph, port, traps = physical_context(synthetic_root)
    coordinator = values["maintenance_coordinator"]
    assert coordinator.registered_writer_count == 19
    with coordinator.maintenance_lease() as issued:
        permit = asdict(issued)
        assert coordinator.maintenance_permit_is_current_v1(permit, lock_backend=values["lock_backend"])
        receipt = values["boundary"](permit)
        assert receipt["ok"] is True, receipt.get("reason")
        assert receipt["multistore_recovery_verified"] is True
        assert values["transaction_port"].call_count == 1
        assert values["resolved_port"].call_count == 1
        assert_cannot_start(graph, port, receipt)
    assert coordinator.maintenance_permit_is_current_v1(permit, lock_backend=values["lock_backend"]) is False
    stale = values["boundary"](permit)
    assert stale["ok"] is False
    assert stale["reason"] == "PERSISTENT_MULTISTORE_RECOVERY_FAILED_CLOSED"
    assert (values["transaction_port"].call_count, values["resolved_port"].call_count) == (1, 1)
    assert_cannot_start(graph, port, stale)
    assert all(trap.calls == 0 for trap in traps)


def test_required_physical_evidence_rejects_synthetic_port_before_second_store(synthetic_root):
    values, graph, port, traps = physical_context(synthetic_root)
    multistore = adapters_v2.CoordinatedMultistoreStartupRecoveryV2(
        replace(values["multistore"]._config, require_physical_recovery_evidence=True),
        transaction_recovery=values["transaction_port"],
        resolved_recovery=values["resolved_port"],
        lock_backend=values["lock_backend"],
        maintenance_coordinator=values["maintenance_coordinator"],
    )
    boundary = boundary_v2.AuthenticatedPersistentAuthorityBoundaryV2(
        replace(values["boundary"]._config,
            expected_multistore_recovery_object_identity_sha256=physical_reference._object_identity(multistore)),
        root_state_provider=values["root_provider"],
        root_authority_verifier=values["verifier"],
        root_revocation_source=values["revocation"],
        multistore_recovery=multistore,
        startup_bridge=values["bridge"],
        clock=values["boundary"]._clock,
    )
    with values["maintenance_coordinator"].maintenance_lease() as issued:
        receipt = boundary(asdict(issued))
        assert receipt["ok"] is False
        assert receipt["reason"] == "PERSISTENT_MULTISTORE_RECOVERY_FAILED_CLOSED"
        assert values["transaction_port"].call_count == 1
        assert values["resolved_port"].call_count == 0
        assert_cannot_start(graph, port, receipt)
    assert all(trap.calls == 0 for trap in traps)


@pytest.mark.parametrize("store,state", [
    ("transaction", "PREPARED"), ("resolved", "RESOLVED"),
])
def test_pending_synthetic_store_blocks_startup_without_repair(synthetic_root, store, state):
    values, graph, port, traps = physical_context(synthetic_root)
    (synthetic_root / f"{store}_recovery_state.json").write_text(
        json.dumps({"state": state, "transactions_remaining": 1}), encoding="utf-8")
    with values["maintenance_coordinator"].maintenance_lease() as issued:
        receipt = values["boundary"](asdict(issued))
    assert receipt["ok"] is False
    assert receipt["reason"] == "PERSISTENT_MULTISTORE_RECOVERY_FAILED_CLOSED"
    assert values["transaction_port"].call_count == 1
    assert values["resolved_port"].call_count == (0 if store == "transaction" else 1)
    assert json.loads((synthetic_root / f"{store}_recovery_state.json").read_text())["state"] == state
    assert_cannot_start(graph, port, receipt)
    assert all(trap.calls == 0 for trap in traps)


@pytest.mark.parametrize("store", ["transaction", "resolved"])
def test_lost_synthetic_store_response_has_no_automatic_retry_or_startup(
    synthetic_root, monkeypatch, store,
):
    values, graph, port, traps = physical_context(synthetic_root)
    target = values[f"{store}_port"]
    original = target.recover_store_v2

    def response_lost(**kwargs):
        original(**kwargs)  # Simulate a completed read with an unreturned receipt.
        raise TimeoutError("synthetic response lost")

    monkeypatch.setattr(target, "recover_store_v2", response_lost)
    with values["maintenance_coordinator"].maintenance_lease() as issued:
        receipt = values["boundary"](asdict(issued))
    assert receipt["ok"] is False
    assert receipt["reason"] == "PERSISTENT_MULTISTORE_RECOVERY_FAILED_CLOSED"
    assert values["transaction_port"].call_count == 1
    assert values["resolved_port"].call_count == (0 if store == "transaction" else 1)
    assert_cannot_start(graph, port, receipt)
    assert all(trap.calls == 0 for trap in traps)


def test_synthetic_boundary_receipt_cannot_attest_an_unbound_prepared_wal(synthetic_root):
    # This is a negative integration check, not a recovery path: the physical
    # reference WAL is deliberately outside the boundary's injected store ports.
    with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as wal_root:
        backend = physical_wal.TemporaryPhysicalDurableRawTransactionBackendV2(
            wal_root, enabled=True,
            scope_attestation=physical_wal.TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2,
            clock=lambda: wal_recovery_harness.SYNTHETIC_NOW_V2,
        )
        backend.initialize_synthetic_registry_offline({"closed_trades": []})
        request = backend.build_transaction_request_offline(
            {"closed_trades": [], "fixture": "unbound-candidate"},
            label="unbound-prepared-wal",
            deadline_epoch=wal_recovery_harness.SYNTHETIC_NOW_V2 + 120,
        )
        backend.prepare_interrupted_transaction_offline(request)
        assert backend.list_prepared_transactions_offline()["prepared_count"] == 1

        values, graph, port, traps = physical_context(synthetic_root)
        with values["maintenance_coordinator"].maintenance_lease() as issued:
            permit = asdict(issued)
            assert issued.registered_writer_count == 19
            assert values["maintenance_coordinator"].maintenance_permit_is_current_v1(
                permit, lock_backend=values["lock_backend"])
            receipt = values["boundary"](permit)
            assert receipt["ok"] is True
            assert receipt["prepared_transactions_after"] == 0
            assert receipt["production_ready"] is False
            assert receipt["synthetic_only"] is True
            assert backend.list_prepared_transactions_offline()["prepared_count"] == 1
            assert_cannot_start(graph, port, receipt)
        assert all(trap.calls == 0 for trap in traps)


@pytest.mark.parametrize("lost_response_store", [None, "transaction", "resolved"])
@pytest.mark.parametrize("collocated,require_aggregate,forge_wal_audit", [
    (False, False, False), (True, True, False), (False, True, False),
    (True, True, True),
])
def test_temporary_physical_stores_recover_inside_current_lease_and_stay_dormant(
    synthetic_root, lost_response_store, collocated, require_aggregate,
    forge_wal_audit,
):
    # These adapters exist only in this test. Both physical stores retain their
    # own internal lock domains; the shared locks here are the injected outer
    # multistore locks, not proof of production writer locking.
    with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as wal_root:
        backend = physical_wal.TemporaryPhysicalDurableRawTransactionBackendV2(
            wal_root, enabled=True,
            scope_attestation=physical_wal.TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2,
            clock=lambda: wal_recovery_harness.SYNTHETIC_NOW_V2,
        )
        backend.initialize_synthetic_registry_offline({"closed_trades": []})
        prepared = backend.build_transaction_request_offline(
            {"closed_trades": [], "fixture": "lease-recovery-candidate"},
            label="lease-bound-prepared-wal",
            deadline_epoch=wal_recovery_harness.SYNTHETIC_NOW_V2 + 120,
        )
        backend.prepare_interrupted_transaction_offline(prepared)
        values = physical_reference.build_authenticated_persistent_authority_production_adapters_context_v2(
            Path(wal_root) if collocated else synthetic_root)
        coordinator = values["maintenance_coordinator"]
        transaction_delegate = values["transaction_port"]
        resolved_delegate = values["resolved_port"]
        guarded_bridge = values["bridge"]
        resolved_store = guarded_bridge._physical_store

        class PhysicalWalTestPort:
            recovery_lock_backend = transaction_delegate.recovery_lock_backend
            recovery_lock_namespace_sha256 = transaction_delegate.recovery_lock_namespace_sha256
            call_count = 0
            terminal_state = None
            receipt = None

            def recover_store_v2(self, *, maintenance_permit, root_authority_attestation, now_epoch):
                self.call_count += 1
                if not coordinator.maintenance_permit_is_current_v1(
                    maintenance_permit, lock_backend=values["lock_backend"]):
                    raise RuntimeError("TEST_PHYSICAL_WAL_MAINTENANCE_NOT_CURRENT")
                snapshot = backend.snapshot_offline()
                catalog = backend.list_prepared_transactions_offline()
                if catalog["prepared_count"] != 1:
                    raise RuntimeError("TEST_PHYSICAL_WAL_PREPARED_COUNT_INVALID")
                batch = wal_contract.build_resumable_recovery_batch_offline_v2(
                    snapshot, catalog,
                    batch_epoch=wal_contract.stable_sha256_v2({"test_batch": catalog["catalog_sha256"]}),
                    deadline_epoch=wal_recovery_harness.SYNTHETIC_NOW_V2 + 120,
                )
                record = catalog["records"][0]
                recovery_request = wal_request_harness.build_synthetic_recovery_request_v2(
                    record, batch, checkpoint_index=0)
                recovery_request["fresh_maintenance_epoch"] = maintenance_permit["maintenance_epoch"]
                recovery_request["request_sha256"] = wal_contract.stable_sha256_v2({
                    key: value for key, value in recovery_request.items() if key != "request_sha256"})
                if not wal_contract.recovery_request_valid_v2(recovery_request, record, batch):
                    raise RuntimeError("TEST_PHYSICAL_WAL_RECOVERY_REQUEST_INVALID")
                recovered = backend.reconcile_attested_transaction_offline(recovery_request)
                if not wal_contract.recovery_result_valid_v2(recovered, recovery_request, 0):
                    raise RuntimeError("TEST_PHYSICAL_WAL_RECOVERY_RESULT_INVALID")
                if backend.list_prepared_transactions_offline()["prepared_count"] != 0:
                    raise RuntimeError("TEST_PHYSICAL_WAL_NOT_DRAINED")
                audit = backend.inspect_transaction_log_offline()
                if not (
                    audit["wal_integrity_verified"] is True
                    and audit["unresolved_prepared_count"] == 0
                    and audit["unresolved_resolved_count"] == 0
                    and audit["backend_instance_sha256"] == recovered["backend_instance_sha256"]
                ):
                    raise RuntimeError("TEST_PHYSICAL_WAL_POSTCONDITION_INVALID")
                if not coordinator.maintenance_permit_is_current_v1(
                    maintenance_permit, lock_backend=values["lock_backend"]):
                    raise RuntimeError("TEST_PHYSICAL_WAL_MAINTENANCE_LOST")
                self.terminal_state = recovered["terminal_state"]
                if lost_response_store == "transaction":
                    raise TimeoutError("synthetic recovery receipt lost after WAL terminal")
                receipt = transaction_delegate.recover_store_v2(
                    maintenance_permit=maintenance_permit,
                    root_authority_attestation=root_authority_attestation,
                    now_epoch=now_epoch)
                evidence = {
                    "evidence_version": adapters_v2.PHYSICAL_STORE_RECOVERY_EVIDENCE_VERSION_V2,
                    "store_role": "TRANSACTION_STORE",
                    "maintenance_epoch": maintenance_permit["maintenance_epoch"],
                    "storage_binding_sha256": receipt["storage_binding_sha256"],
                    "source_store_instance_sha256": recovered["backend_instance_sha256"],
                    "source_receipt_sha256": recovered["result_sha256"],
                    "postcondition_receipt_sha256": audit["audit_sha256"],
                    "unresolved_transactions_remaining": 0,
                    "physical_store_accessed": True,
                    "temporary_storage_only": True,
                    "synthetic_only": True,
                    "production_authority": False,
                }
                if forge_wal_audit:
                    evidence["postcondition_receipt_sha256"] = "0" * 64
                evidence["evidence_sha256"] = adapters_v2.physical_store_recovery_evidence_sha256_v2(evidence)
                receipt["physical_recovery_evidence"] = evidence
                receipt["receipt_sha256"] = adapters_v2.store_recovery_port_receipt_sha256_v2(receipt)
                self.receipt = receipt
                return receipt

        class PhysicalResolvedTestPort:
            recovery_lock_backend = resolved_delegate.recovery_lock_backend
            recovery_lock_namespace_sha256 = resolved_delegate.recovery_lock_namespace_sha256
            call_count = 0
            physical_receipts = None
            receipt = None

            def recover_store_v2(self, *, maintenance_permit, root_authority_attestation, now_epoch):
                self.call_count += 1
                if not coordinator.maintenance_permit_is_current_v1(
                    maintenance_permit, lock_backend=values["lock_backend"]):
                    raise RuntimeError("TEST_PHYSICAL_RESOLVED_MAINTENANCE_NOT_CURRENT")
                opened = resolved_store.open_offline(now_epoch=now_epoch)
                recovered = resolved_store.recover_offline(now_epoch=now_epoch)
                scanned = resolved_store.read_resolved_records_offline(now_epoch=now_epoch)
                self.physical_receipts = (opened, recovered, scanned)
                if not (
                    all(result.get("ok") is True for result in self.physical_receipts)
                    and recovered.get("root_signature_reverified") is True
                    and recovered.get("root_revocation_checked") is True
                    and scanned.get("complete_scan_verified") is True
                    and scanned.get("wal_integrity_verified") is True
                    and scanned.get("record_count") == 0
                    and scanned.get("real_registry_accessed") is False
                    and scanned.get("network_accessed") is False
                    and scanned.get("broker_called") is False
                    and all(
                        result.get("receipt_sha256") ==
                        resolved_reference.resolved_authority_physical_store_reference_receipt_sha256_v2({
                            key: value for key, value in result.items()
                            if key not in {"ok", "status", "reason", "observed"}
                        })
                        for result in self.physical_receipts
                    )
                    and coordinator.maintenance_permit_is_current_v1(
                        maintenance_permit, lock_backend=values["lock_backend"])
                ):
                    raise RuntimeError("TEST_PHYSICAL_RESOLVED_RECOVERY_INVALID")
                receipt = resolved_delegate.recover_store_v2(
                    maintenance_permit=maintenance_permit,
                    root_authority_attestation=root_authority_attestation,
                    now_epoch=now_epoch)
                if lost_response_store == "resolved":
                    raise TimeoutError("synthetic receipt lost after physical RESOLVED recovery")
                evidence = {
                    "evidence_version": adapters_v2.PHYSICAL_STORE_RECOVERY_EVIDENCE_VERSION_V2,
                    "store_role": "RESOLVED_AUTHORITY_STORE",
                    "maintenance_epoch": maintenance_permit["maintenance_epoch"],
                    "storage_binding_sha256": receipt["storage_binding_sha256"],
                    "source_store_instance_sha256": recovered["ledger_object_identity_sha256"],
                    "source_receipt_sha256": recovered["receipt_sha256"],
                    "postcondition_receipt_sha256": scanned["receipt_sha256"],
                    "unresolved_transactions_remaining": 0,
                    "physical_store_accessed": True,
                    "temporary_storage_only": True,
                    "synthetic_only": True,
                    "production_authority": False,
                }
                evidence["evidence_sha256"] = adapters_v2.physical_store_recovery_evidence_sha256_v2(evidence)
                receipt["physical_recovery_evidence"] = evidence
                receipt["receipt_sha256"] = adapters_v2.store_recovery_port_receipt_sha256_v2(receipt)
                self.receipt = receipt
                return receipt

        physical_port = PhysicalWalTestPort()
        physical_resolved_port = PhysicalResolvedTestPort()
        observation_lease = None
        collector = None
        if require_aggregate:
            ledger = resolved_store._ledger
            observation_lease = observation_lease_harness.make_physical_multistore_observation_lease_v2(
                backend=backend, ledger=ledger, clock=values["boundary"]._clock)
            collector = aggregate_collection_harness.make_physical_locked_aggregate_collection_v2(
                observation_lease=observation_lease, backend=backend,
                ledger=ledger, clock=values["boundary"]._clock)
        multistore = adapters_v2.CoordinatedMultistoreStartupRecoveryV2(
            replace(values["multistore"]._config,
                expected_transaction_recovery_object_identity_sha256=physical_reference._object_identity(physical_port),
                expected_resolved_recovery_object_identity_sha256=physical_reference._object_identity(physical_resolved_port),
                require_physical_recovery_evidence=True),
            transaction_recovery=physical_port, resolved_recovery=physical_resolved_port,
            lock_backend=values["lock_backend"], maintenance_coordinator=coordinator)
        boundary = boundary_v2.AuthenticatedPersistentAuthorityBoundaryV2(
            replace(values["boundary"]._config,
                expected_multistore_recovery_object_identity_sha256=physical_reference._object_identity(multistore),
                expected_startup_bridge_object_identity_sha256=physical_reference._object_identity(guarded_bridge),
                require_locked_physical_aggregate=require_aggregate,
                expected_locked_physical_aggregate_collector_object_identity_sha256=(
                    physical_reference._object_identity(collector) if collector is not None else None)),
            root_state_provider=values["root_provider"], root_authority_verifier=values["verifier"],
            root_revocation_source=values["revocation"], multistore_recovery=multistore,
            startup_bridge=guarded_bridge, locked_physical_aggregate_collector=collector,
            clock=values["boundary"]._clock)
        d, traps = fixture()
        receipt_port = ReceiptPort()
        d = replace(d, ports=replace(d.ports, startup_state=receipt_port),
            root_state_provider=values["root_provider"], root_authority_verifier=values["verifier"],
            root_revocation_source=values["revocation"], multistore_recovery=multistore,
            startup_bridge=guarded_bridge, clock=boundary._clock)
        graph = assembly.assemble_c3_dependencies_offline_v1(d)
        with coordinator.maintenance_lease() as issued:
            receipt = boundary(asdict(issued))
            assert physical_port.call_count == 1
            assert physical_port.terminal_state == "ABORTED"
            if lost_response_store is not None:
                assert receipt["ok"] is False
                assert receipt["reason"] == "PERSISTENT_MULTISTORE_RECOVERY_FAILED_CLOSED"
                assert transaction_delegate.call_count == (0 if lost_response_store == "transaction" else 1)
                assert physical_resolved_port.call_count == (0 if lost_response_store == "transaction" else 1)
                assert resolved_delegate.call_count == (0 if lost_response_store == "transaction" else 1)
            elif require_aggregate and (not collocated or forge_wal_audit):
                assert receipt["ok"] is False
                assert receipt["reason"] == "AUTHENTICATED_PHYSICAL_AGGREGATE_RECEIPT_INVALID"
                assert transaction_delegate.call_count == 1
                assert resolved_delegate.call_count == 1
                assert observation_lease.snapshot()["held_lock_count"] == 0
            else:
                assert receipt["ok"] is True, receipt.get("reason")
                assert receipt["multistore_recovery_verified"] is True
                assert receipt["locked_physical_aggregate_verified"] is require_aggregate
                if require_aggregate:
                    assert receipt["locked_physical_aggregate_receipt_sha256"]
                    assert observation_lease.snapshot()["held_lock_count"] == 0
                assert transaction_delegate.call_count == 1
                assert physical_resolved_port.call_count == 1
                assert resolved_delegate.call_count == 1
                transaction_receipt = physical_port.receipt
                resolved_receipt = physical_resolved_port.receipt
                assert adapters_v2.CoordinatedMultistoreStartupRecoveryV2._port_receipt_valid(
                    transaction_receipt, "TRANSACTION_STORE", True)
                assert adapters_v2.CoordinatedMultistoreStartupRecoveryV2._port_receipt_valid(
                    resolved_receipt, "RESOLVED_AUTHORITY_STORE", True)
                missing = copy.deepcopy(transaction_receipt)
                del missing["physical_recovery_evidence"]
                missing["receipt_sha256"] = adapters_v2.store_recovery_port_receipt_sha256_v2(missing)
                assert not adapters_v2.CoordinatedMultistoreStartupRecoveryV2._port_receipt_valid(
                    missing, "TRANSACTION_STORE", True)
                swapped = copy.deepcopy(transaction_receipt)
                swapped["physical_recovery_evidence"] = copy.deepcopy(
                    resolved_receipt["physical_recovery_evidence"])
                swapped["receipt_sha256"] = adapters_v2.store_recovery_port_receipt_sha256_v2(swapped)
                assert not adapters_v2.CoordinatedMultistoreStartupRecoveryV2._port_receipt_valid(
                    swapped, "TRANSACTION_STORE", True)
                # Re-read the physical RESOLVED source after the boundary's
                # bridge has run, not from the port's cached scan result.
                fresh_resolved_scan = resolved_store.read_resolved_records_offline(
                    now_epoch=boundary._clock())
                assert fresh_resolved_scan["ok"] is True, fresh_resolved_scan.get("reason")
                assert fresh_resolved_scan["record_count"] == 0
                assert fresh_resolved_scan["receipt_sha256"] == resolved_receipt[
                    "physical_recovery_evidence"]["postcondition_receipt_sha256"]
            if physical_resolved_port.call_count:
                assert physical_resolved_port.physical_receipts is not None
                assert all(result["filesystem_accessed"] is True for result in physical_resolved_port.physical_receipts)
            assert backend.list_prepared_transactions_offline()["prepared_count"] == 0
            assert receipt["production_ready"] is False and receipt["synthetic_only"] is True
            assert_cannot_start(graph, receipt_port, receipt)
        reopened = physical_wal.TemporaryPhysicalDurableRawTransactionBackendV2(
            wal_root, enabled=True,
            scope_attestation=physical_wal.TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2,
            clock=lambda: wal_recovery_harness.SYNTHETIC_NOW_V2,
        )
        assert reopened.list_prepared_transactions_offline()["prepared_count"] == 0
        reopened_audit = reopened.inspect_transaction_log_offline()
        assert reopened_audit["latest_state_counts"]["ABORTED"] == 1
        if lost_response_store is None:
            assert reopened_audit["backend_instance_sha256"] == physical_port.receipt[
                "physical_recovery_evidence"]["source_store_instance_sha256"]
            if forge_wal_audit:
                assert reopened_audit["audit_sha256"] != physical_port.receipt[
                    "physical_recovery_evidence"]["postcondition_receipt_sha256"]
            else:
                assert reopened_audit["audit_sha256"] == physical_port.receipt[
                    "physical_recovery_evidence"]["postcondition_receipt_sha256"]
        assert all(trap.calls == 0 for trap in traps)
