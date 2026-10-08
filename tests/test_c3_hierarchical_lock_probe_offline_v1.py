"""Temporary lock hierarchy only; never import or execute main.py."""

from itertools import count
import json
from pathlib import Path
import socket
import subprocess
import sys

import pytest

import trade_registry_c3_hierarchical_lock_probe_offline_v1 as hierarchy_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_physical_conformance_adapter_offline_harness_v2 as physical_harness
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_v1
import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as storage_v1


@pytest.fixture(autouse=True)
def deny_external(monkeypatch):
    original_popen = subprocess.Popen
    def forbidden(*_args, **_kwargs):
        raise AssertionError("C3_HIERARCHY_EXTERNAL_ACTION_FORBIDDEN")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    return original_popen


@pytest.fixture
def temporary_hierarchy():
    with physical_harness.synthetic_physical_conformance_context_v2() as values:
        root = values["backend"]._root
        outer = storage_v1.CrossPlatformInterprocessFileLockBackendV1(
            root / "outer-writer-locks", enabled=True,
        )
        lease_store = storage_v1.DurableJsonMaintenanceLeaseStoreV1(
            outer.storage_root, enabled=True,
        )
        nonce = count()
        coordinator = coordinator_v1.ClosedRepairWriterRuntimeCoordinatorV1(
            config=coordinator_v1.WriterRuntimeCoordinatorConfigV1(
                enabled=True, maintenance_only=False, lock_timeout_seconds=0.05,
            ),
            lock_backend=outer,
            lease_store=lease_store,
            clock=lambda: float(physical_harness.SYNTHETIC_NOW_V2),
            nonce_source=lambda: f"synthetic-hierarchy-{next(nonce)}",
        )
        coordinator.register_all_declared_writers()
        yield {
            "coordinator": coordinator,
            "wal_backend": values["backend"],
            "resolved_ledger": values["resolved_ledger"],
            "observation_lease": values["observation_lease"],
            "aggregate_collector": values["locked_collection"],
        }


def probe(values, *, enabled=True):
    return hierarchy_v1.probe_c3_hierarchical_locks_offline_v1(
        enabled=enabled, **values,
    )


def test_default_off_does_not_inspect_dependencies():
    class Explosive:
        def __getattribute__(self, _name):
            raise AssertionError("default-off must not inspect dependencies")

    result = hierarchy_v1.probe_c3_hierarchical_locks_offline_v1(
        coordinator=Explosive(), wal_backend=Explosive(),
    )
    assert result["reason"] == "C3_HIERARCHICAL_LOCK_PROBE_DEFAULT_OFF"
    assert result["writer_lock_probes_verified"] == 0
    assert result["production_ready"] is False


def test_outer_writer_and_maintenance_lock_allows_ordered_inner_collection(temporary_hierarchy):
    result = probe(temporary_hierarchy)
    assert result["ok"] is True, result["reason"]
    assert result["writer_lock_probes_verified"] == 19
    assert result["maintenance_lock_verified"] is True
    assert result["inner_lock_order_verified"] is True
    assert result["inner_contention_verified"] is True
    assert result["aggregate_collection_verified"] is True
    assert result["all_locks_released"] is True
    assert result["cross_process_verified"] is False
    assert result["runtime_writers_verified"] is False
    assert result["production_ready"] is False
    assert result["live_allowed"] is False


def test_colliding_outer_and_wal_lock_fails_before_acquisition(temporary_hierarchy, monkeypatch):
    monkeypatch.setattr(
        temporary_hierarchy["coordinator"], "_lock_backend",
        temporary_hierarchy["wal_backend"]._lock_backend,
    )
    result = probe(temporary_hierarchy)
    assert result["reason"] == "C3_HIERARCHICAL_LOCK_PROBE_LOCK_DOMAINS_NOT_DISTINCT"
    assert result["writer_lock_probes_verified"] == 0


def test_swapped_inner_lock_order_fails_before_acquisition(temporary_hierarchy, monkeypatch):
    lease = temporary_hierarchy["observation_lease"]
    specs = lease._specs()
    monkeypatch.setattr(lease, "_specs", lambda: tuple(reversed(specs)))
    result = probe(temporary_hierarchy)
    assert result["reason"] == "C3_HIERARCHICAL_LOCK_PROBE_INNER_ORDER_INVALID"
    assert result["writer_lock_probes_verified"] == 0


def test_missing_writer_registration_fails_before_acquisition(temporary_hierarchy):
    coordinator = temporary_hierarchy["coordinator"]
    coordinator._registered.pop(next(iter(coordinator._registered)))
    result = probe(temporary_hierarchy)
    assert result["reason"] == "C3_HIERARCHICAL_LOCK_PROBE_TEMPORARY_WRITERS_REQUIRED"
    assert result["writer_lock_probes_verified"] == 0


def test_contended_inner_wal_lock_fails_and_releases_outer(temporary_hierarchy):
    wal = temporary_hierarchy["wal_backend"]
    coordinator = temporary_hierarchy["coordinator"]
    holder = storage_v1.CrossPlatformInterprocessFileLockBackendV1(
        wal._lock_backend.storage_root, enabled=True,
    ).acquire(wal._lock_namespace(), 0.01)
    assert holder is not None
    try:
        result = probe(temporary_hierarchy)
        assert result["reason"] == "C3_HIERARCHICAL_LOCK_PROBE_WAL_INNER_LOCK_UNAVAILABLE"
        outer_competitor = storage_v1.CrossPlatformInterprocessFileLockBackendV1(
            coordinator._lock_backend.storage_root, enabled=True,
        )
        outer_handle = outer_competitor.acquire(coordinator.lock_namespace, 0.01)
        assert outer_handle is not None
        outer_handle.release()
    finally:
        holder.release()


def test_invalid_enable_type_fails_closed():
    result = hierarchy_v1.probe_c3_hierarchical_locks_offline_v1(enabled=1)
    assert result["reason"] == "C3_HIERARCHICAL_LOCK_PROBE_ENABLE_INVALID"


def test_synthetic_recovery_owner_is_default_off_and_requires_explicit_enable(tmp_path):
    assert coordinator_v1.WriterRuntimeCoordinatorConfigV1().synthetic_recovery_owner_identity is None
    with pytest.raises(ValueError, match="synthetic recovery owner identity"):
        coordinator_v1.WriterRuntimeCoordinatorConfigV1(
            synthetic_recovery_owner_identity="synthetic-owner",
        )
    with pytest.raises(ValueError, match="synthetic recovery owner identity"):
        coordinator_v1.WriterRuntimeCoordinatorConfigV1(
            enabled=True, synthetic_recovery_owner_identity=" ",
        )

    lock = storage_v1.CrossPlatformInterprocessFileLockBackendV1(
        tmp_path / "noncanonical-lock-root", enabled=True,
    )
    store = storage_v1.DurableJsonMaintenanceLeaseStoreV1(
        lock.storage_root, enabled=True,
    )
    coordinator = coordinator_v1.ClosedRepairWriterRuntimeCoordinatorV1(
        config=coordinator_v1.WriterRuntimeCoordinatorConfigV1(
            enabled=True, synthetic_recovery_owner_identity="synthetic-owner",
        ),
        lock_backend=lock,
        lease_store=store,
        clock=lambda: 1.0,
        nonce_source=lambda: "synthetic-nonce",
    )
    coordinator.register_all_declared_writers()
    with pytest.raises(
        coordinator_v1.WriterRuntimeCoordinationBlocked,
        match="SYNTHETIC_STALE_LEASE_RECOVERY_TEMPORARY_STORAGE_REQUIRED",
    ):
        with coordinator.maintenance_lease():
            pytest.fail("noncanonical store must not acquire maintenance")
    assert store.read(coordinator.lock_namespace) is None
    recovery = coordinator_v1.recover_stale_maintenance_lease_v1(
        enabled=True,
        scope_attestation=coordinator_v1.SYNTHETIC_STALE_LEASE_RECOVERY_ATTESTATION_V1,
        lock_backend=lock,
        lease_store=store,
        clock=lambda: 100.0,
        current_process_identity="synthetic-recovery-probe",
        owner_liveness=lambda _owner: False,
    )
    assert recovery["ok"] is False
    assert recovery["reason"] == "STALE_LEASE_RECOVERY_SYNTHETIC_TEMPORARY_STORAGE_REQUIRED"
    assert not list(lock.storage_root.glob("*.writer.lock"))


def test_runtime_remains_unwired():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "trade_registry_c3_hierarchical_lock_probe_offline_v1" not in source


@pytest.mark.skipif(sys.platform != "linux", reason="requires isolated Linux lab")
def test_cross_process_outer_and_inner_contention_releases(
    temporary_hierarchy, monkeypatch, deny_external,
):
    """A fixed read-only child disputes only the three synthetic lock domains."""
    values = temporary_hierarchy
    root = Path(values["wal_backend"]._root).resolve(strict=True)
    coordinator = values["coordinator"]
    observation_lease = values["observation_lease"]
    specs = observation_lease._specs()
    assert tuple(spec[0].storage_root.parent for spec in specs) == (root, root)
    domains = {
        "outer-writer-locks": coordinator.lock_namespace,
        "locks": specs[0][1],
        "resolved-authority": specs[1][1],
        "writer-admission": coordinator.lock_namespace,
        "maintenance-crash": coordinator.lock_namespace,
        "maintenance-crash-attested": coordinator.lock_namespace,
    }
    assert coordinator._lock_backend.storage_root.parent == root
    assert specs[0][0].storage_root.name == "locks"
    assert specs[1][0].storage_root.name == "resolved-authority"
    marker = root / "synthetic-cross-process-lock-probe-v1"
    marker.write_text("synthetic-c3-hierarchical-lock-probe-v1", encoding="ascii")
    helper = Path(__file__).parent / "helpers" / "c3_hierarchical_lock_child.py"
    prefix = [sys.executable, "-I", "-B", str(helper.resolve()), str(root)]
    child_env = {}
    allowed = {
        tuple(prefix + [role, namespace])
        for role, namespace in domains.items() if role != "writer-admission"
    }
    allowed.update(
        tuple(prefix + ["writer-admission", coordinator.lock_namespace, str(index)])
        for index in range(19)
    )
    children = []

    def allowed_popen(args, **kwargs):
        if (
            not isinstance(args, list)
            or tuple(args) not in allowed
            or kwargs != dict(
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, env=child_env, cwd=str(root),
            )
        ):
            raise AssertionError("only fixed synthetic lock children are permitted")
        child = deny_external(args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", allowed_popen)

    def child_result(role, writer_index=None, expected_code=0):
        args = prefix + [role, domains[role]]
        if writer_index is not None:
            args.append(str(writer_index))
        child = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=child_env, cwd=str(root),
        )
        out, err = child.communicate(timeout=10)
        assert child.returncode == expected_code, (child.returncode, err)
        assert not err
        result = json.loads(out)
        assert result["synthetic_only"] is True
        assert result["role"] == role
        result["child_pid"] = child.pid
        return result

    def child_acquires(role):
        return child_result(role)["acquired"]

    try:
        writer_id = coordinator_v1.canonical_runtime_writer_inventory_v1()[0]["writer_id"]
        with coordinator.mutation(writer_id):
            assert child_acquires("outer-writer-locks") is False
        assert child_acquires("outer-writer-locks") is True
        outer_holder = coordinator._lock_backend.acquire(coordinator.lock_namespace, 0.03)
        assert outer_holder is not None
        try:
            for index, writer in enumerate(coordinator_v1.canonical_runtime_writer_inventory_v1()):
                result = child_result("writer-admission", index)
                assert result["writer_id"] == writer["writer_id"]
                assert result["admitted"] is False
                assert result["reason"] == "SHARED_LOCK_TIMEOUT"
        finally:
            outer_holder.release()
        for index, writer in enumerate(coordinator_v1.canonical_runtime_writer_inventory_v1()):
            result = child_result("writer-admission", index)
            assert result["writer_id"] == writer["writer_id"]
            assert result["admitted"] is True
            assert result["reason"] is None
        with coordinator.maintenance_lease():
            assert child_acquires("outer-writer-locks") is False
            maintenance_result = child_result("writer-admission", 0)
            assert maintenance_result["admitted"] is False
            assert maintenance_result["reason"] == "MAINTENANCE_LEASE_ACTIVE"
            with observation_lease.hold_offline(
                expires_at_epoch=observation_lease._clock() + 60,
            ):
                assert child_acquires("locks") is False
                assert child_acquires("resolved-authority") is False
            assert child_acquires("locks") is True
            assert child_acquires("resolved-authority") is True
            assert child_acquires("outer-writer-locks") is False
        assert child_acquires("outer-writer-locks") is True
        attested = child_result("maintenance-crash-attested", expected_code=75)
        assert attested["state"] == "QUIESCED"
        assert attested["process_id"] == attested["child_pid"]
        assert child_acquires("outer-writer-locks") is True
        owner_sha = coordinator_v1._stable_sha256({
            "process_identity": f"synthetic-maintenance-child-{attested['process_id']}"
        })
        attested_lease = coordinator._lease_store.read(coordinator.lock_namespace)
        assert attested_lease["state"] == "QUIESCED"
        assert attested_lease["owner_identity_sha256"] == owner_sha
        assert attested_lease["recovery_scope_attestation"] == (
            coordinator_v1.SYNTHETIC_STALE_LEASE_RECOVERY_ATTESTATION_V1
        )
        unknown = coordinator_v1.recover_stale_maintenance_lease_v1(
            enabled=True,
            scope_attestation=coordinator_v1.SYNTHETIC_STALE_LEASE_RECOVERY_ATTESTATION_V1,
            lock_backend=coordinator._lock_backend,
            lease_store=coordinator._lease_store,
            clock=lambda: 100.0,
            current_process_identity="synthetic-parent-unknown-owner",
            owner_liveness=lambda _owner: None,
            stale_after_seconds=1.0,
            lock_timeout_seconds=0.03,
        )
        assert unknown["reason"] == "STALE_LEASE_OWNER_LIVENESS_UNKNOWN"
        assert coordinator._lease_store.read(coordinator.lock_namespace)["state"] == "QUIESCED"
        recovered = coordinator_v1.recover_stale_maintenance_lease_v1(
            enabled=True,
            scope_attestation=coordinator_v1.SYNTHETIC_STALE_LEASE_RECOVERY_ATTESTATION_V1,
            lock_backend=coordinator._lock_backend,
            lease_store=coordinator._lease_store,
            clock=lambda: 100.0,
            current_process_identity="synthetic-parent-after-attested-crash",
            owner_liveness=lambda owner: False if owner == owner_sha else None,
            stale_after_seconds=1.0,
            lock_timeout_seconds=0.03,
        )
        assert recovered["ok"] is True, recovered["reason"]
        assert recovered["recovery_performed"] is True
        assert coordinator._lease_store.read(coordinator.lock_namespace)["state"] == "RELEASED"
        assert child_result("writer-admission", 0)["admitted"] is True
        crashed = child_result("maintenance-crash", expected_code=75)
        assert crashed["state"] == "QUIESCED"
        assert child_acquires("outer-writer-locks") is True
        persisted = coordinator._lease_store.read(coordinator.lock_namespace)
        assert persisted["state"] == "QUIESCED"
        blocked = child_result("writer-admission", 0)
        assert blocked["admitted"] is False
        assert blocked["reason"] == "MAINTENANCE_LEASE_ACTIVE"
        recovery = coordinator_v1.recover_stale_maintenance_lease_v1(
            enabled=True,
            scope_attestation=coordinator_v1.SYNTHETIC_STALE_LEASE_RECOVERY_ATTESTATION_V1,
            lock_backend=coordinator._lock_backend,
            lease_store=coordinator._lease_store,
            clock=lambda: 100.0,
            current_process_identity="synthetic-parent-after-crash",
            owner_liveness=lambda _owner: False,
            stale_after_seconds=1.0,
            lock_timeout_seconds=0.03,
        )
        assert recovery["ok"] is False
        assert recovery["reason"] == "STALE_LEASE_RECOVERY_ATTESTATION_INVALID"
        assert coordinator._lease_store.read(coordinator.lock_namespace)["state"] == "QUIESCED"
        with pytest.raises(AssertionError, match="only fixed synthetic"):
            subprocess.Popen([sys.executable, "-c", "pass"])
        with pytest.raises(AssertionError, match="C3_HIERARCHY_EXTERNAL_ACTION_FORBIDDEN"):
            socket.create_connection(("127.0.0.1", 1))
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)
