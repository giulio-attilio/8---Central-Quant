"""Synthetic operations and temporary files only; no application startup."""

from __future__ import annotations

import copy
import importlib
import socket
import subprocess
import tempfile
import threading
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def deny_external_access(monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError("external access forbidden in offline tests")
    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)


@pytest.fixture
def env(tmp_path):
    m = importlib.import_module("trade_registry_c3_maintenance_activation_offline_v1")
    c = m.coordinator_module
    s = c.runtime_storage
    root = tmp_path / "synthetic-coordination"
    registry_path = tmp_path / "synthetic-trade-registry.json"
    flushes = []
    # File fsync/replace and OS locks are real. Directory fsync is a synthetic
    # port here: this test does not attest Linux/Render crash durability.
    locks = s.CrossPlatformInterprocessFileLockBackendV1(root, enabled=True)
    leases = s.DurableJsonMaintenanceLeaseStoreV1(
        root, enabled=True, directory_fsync=flushes.append,
    )
    e = SimpleNamespace(m=m, c=c, s=s, root=root, registry_path=registry_path,
                        locks=locks, leases=leases,
                        time=100.0, controls=dict(m._SAFE_CONTROL_VECTOR), kill=False,
                        calls=[], permits=[], flushes=flushes, bindings=[], consumed=False)
    e.request = object()

    def authorize(request, binding):
        e.bindings.append(binding)
        if request is not e.request or e.consumed:
            return False
        e.consumed = True
        return True

    def result(phase, permit, _deadline):
        assert e.leases.read(e.c.canonical_runtime_lock_namespace_v1())["state"] == "QUIESCED"
        e.calls.append(phase)
        e.permits.append(permit)
        common = dict(ok=True, maintenance_permit=permit, synthetic_only=True,
                      registry_write=False, no_order_sent=True)
        if phase == "bootstrap":
            return dict(common, migration_done=True, restart_readiness_attested=True,
                        last_load_ok=True, last_write_ok=True, write_allowed=True,
                        temporary_read_only=False)
        if phase == "recovery":
            return dict(common, startup_recovery_verified=True,
                        prepared_transactions_after=0, resolved_transactions_after=0,
                        unresolved_transactions_after=0)
        return dict(common, registry_storage_ready=True, startup_recovery_verified=True,
                    blocking_failures=0, runtime_activation_allowed=False, live_allowed=False)

    e.options = dict(
        config=m.MaintenanceActivationConfigV1(
            enabled=True, scope_attestation=m.OFFLINE_MAINTENANCE_SCOPE,
            max_duration_seconds=10, lock_timeout_seconds=0.02,
        ),
        lock_backend=locks, lease_store=leases,
        storage_root_binding_sha256=c.production_coordinator_storage_root_binding_sha256_v1(root),
        registry_path=str(registry_path),
        clock=lambda: e.time, nonce_source=lambda: "synthetic-nonce",
        consume_authorization=authorize, trading_controls=lambda: copy.deepcopy(e.controls),
        kill_switch=lambda: e.kill,
        bootstrap=lambda p, d: result("bootstrap", p, d),
        startup_recovery=lambda p, d: result("recovery", p, d),
        postflight=lambda p, d: result("postflight", p, d),
    )
    e.build = lambda **overrides: m.OfflineMaintenanceActivationV1(**(e.options | overrides))
    e.lease = lambda: leases.read(c.canonical_runtime_lock_namespace_v1())
    return e


def test_default_off_does_not_inspect_request_or_any_dependency(env):
    def bomb(*_args):
        pytest.fail("dormant composition touched a dependency")
    composition = env.build(config=env.m.MaintenanceActivationConfigV1(),
                            clock=bomb, trading_controls=bomb, consume_authorization=bomb)
    before = list(env.root.iterdir())
    assert composition.run_offline(object())["status"] == "C3_MAINTENANCE_DEFAULT_OFF"
    assert list(env.root.iterdir()) == before == []


def test_enabled_coordinator_requires_explicit_colocated_registry_path(env, tmp_path):
    config = env.c.ProductionWriterRuntimeCoordinatorBindingConfigV1(
        enabled=True,
        scope_attestation=env.c.PRODUCTION_COORDINATOR_EXPLICIT_DEPENDENCY_BINDING_ATTESTATION_V1,
        storage_root_binding_sha256=env.options["storage_root_binding_sha256"],
    )
    def build(path):
        return env.c.build_production_closed_repair_writer_runtime_coordinator_v1(
            config=config, lock_backend=env.locks, lease_store=env.leases,
            registry_path=path, clock=env.options["clock"],
            nonce_source=env.options["nonce_source"],
        )
    before = list(env.root.iterdir())
    for path in (None, "relative-registry.json", tmp_path / "other" / "registry.json"):
        with pytest.raises(env.c.WriterRuntimeCoordinationBlocked,
                           match="PRODUCTION_COORDINATOR_REGISTRY_STORAGE_BINDING_INVALID"):
            build(path)
    assert list(env.root.iterdir()) == before == []
    coordinator = build(env.registry_path)
    assert coordinator._registry_path_binding == env.registry_path.resolve()
    assert coordinator.enabled is True
    assert list(env.root.iterdir()) == []


def test_offline_maintenance_rejects_mismatched_registry_before_steps(env, tmp_path):
    result = env.build(registry_path=str(tmp_path / "other" / "registry.json")).run_offline(env.request)
    assert result["status"] == "C3_MAINTENANCE_COORDINATOR_BLOCKED"
    assert env.calls == []
    assert list(env.root.iterdir()) == []


def test_complete_chain_uses_one_physical_coordinator_and_exact_permit(env):
    composition = env.build()
    outcome = composition.run_offline(env.request)
    assert outcome["ok"] is True
    assert env.calls == ["bootstrap", "recovery", "postflight"]
    assert all(p is env.permits[0] for p in env.permits)
    assert composition._coordinator._lock_backend is env.locks
    assert composition._coordinator._lease_store is env.leases
    assert composition._coordinator.registered_writer_count == 19
    assert env.lease()["state"] == "RELEASED"
    assert env.lease()["maintenance_epoch"] == env.permits[0].maintenance_epoch
    assert len(env.flushes) == 4
    assert outcome["runtime_activation_allowed"] is False
    assert outcome["production_ready"] is False
    assert outcome["coordination_ready"] is False
    assert outcome["live_allowed"] is False
    assert "synthetic-nonce" not in repr(env.bindings[0])
    assert str(env.root) not in repr(composition)
    assert composition.run_offline(env.request)["status"].endswith("ALREADY_CONSUMED")


def test_every_writer_denied_even_after_successful_maintenance(env):
    composition = env.build()
    assert composition.run_offline(env.request)["ok"] is True
    for entry in env.c.canonical_runtime_writer_inventory_v1():
        with pytest.raises(env.c.WriterRuntimeCoordinationBlocked, match="MAINTENANCE_ONLY_WRITERS_FORBIDDEN"):
            with composition._coordinator.mutation(entry["writer_id"]):
                pytest.fail("writer admitted")


def test_disabling_a_maintenance_binding_does_not_restore_writer_passthrough(env):
    coordinator = env.c.build_production_closed_repair_writer_runtime_coordinator_v1(
        config=env.c.ProductionWriterRuntimeCoordinatorBindingConfigV1(maintenance_only=True)
    )
    assert coordinator.enabled is False
    assert coordinator.maintenance_only is True
    with pytest.raises(env.c.WriterRuntimeCoordinationBlocked, match="MAINTENANCE_ONLY_WRITERS_FORBIDDEN"):
        with coordinator.mutation("MAIN_TRADE_REGISTRY_STORAGE_BOOTSTRAP"):
            pytest.fail("disabled maintenance became uncoordinated passthrough")


@pytest.mark.parametrize("reply", [False, None, 1, {"authenticated": True}])
def test_authentication_requires_explicit_trusted_verifier_acceptance(env, reply):
    result = env.build(consume_authorization=lambda *_: reply).run_offline(env.request)
    assert result["status"] == "C3_MAINTENANCE_AUTHORIZATION_DENIED"
    assert env.calls == []
    assert list(env.root.iterdir()) == []


def test_hashes_in_a_request_do_not_grant_authentication(env):
    result = env.build().run_offline({"authenticated": True, "sha256": "a" * 64})
    assert result["status"] == "C3_MAINTENANCE_AUTHORIZATION_DENIED"
    assert env.calls == []


def test_verifier_receives_scope_root_nonce_and_deadline(env):
    assert env.build().run_offline(env.request)["ok"] is True
    binding = env.bindings[0]
    assert binding.scope == env.m.OFFLINE_MAINTENANCE_SCOPE
    assert binding.storage_root_binding_sha256 == env.options["storage_root_binding_sha256"]
    assert binding.deadline == 110.0 and binding.writer_count == 19
    assert binding.maintenance_only is True
    assert env.build().run_offline(env.request)["status"] == "C3_MAINTENANCE_AUTHORIZATION_DENIED"


@pytest.mark.parametrize("key,value", [
    ("enable_real_trading", True), ("broker_dry_run", False), ("falcon_mode", "LIVE"),
    ("central_real_execution_enabled", True), ("central_real_pilot_enabled", True),
    ("live_trading_enabled", True), ("order_submission_authorized", True),
    ("enable_real_trading", 0), ("broker_dry_run", 1),
])
def test_full_safe_control_vector_required_before_authorization(env, key, value):
    env.controls[key] = value
    result = env.build().run_offline(env.request)
    assert result["status"] == "C3_MAINTENANCE_CONTROLS_UNSAFE"
    assert env.calls == env.bindings == []


@pytest.mark.parametrize("changed", ["kill", "deadline", "controls", "clock_regression"])
def test_changes_after_bootstrap_stop_recovery_and_release_lease(env, changed):
    bootstrap = env.options["bootstrap"]
    def first(permit, deadline):
        result = bootstrap(permit, deadline)
        if changed == "kill":
            env.kill = True
        elif changed == "deadline":
            env.time = deadline
        elif changed == "clock_regression":
            env.time -= 1
        else:
            env.controls["broker_dry_run"] = False
        return result
    result = env.build(bootstrap=first).run_offline(env.request)
    assert result["ok"] is False
    assert env.calls == ["bootstrap"]
    assert env.lease()["state"] == ("QUIESCED" if changed == "clock_regression" else "RELEASED")
    handle = env.locks.acquire(env.c.canonical_runtime_lock_namespace_v1(), 0.02)
    assert handle is not None
    handle.release()


@pytest.mark.parametrize("phase", ["bootstrap", "startup_recovery", "postflight"])
@pytest.mark.parametrize("failure", ["exception", "permit_copy", "false_ok", "real_data"])
def test_bad_step_stops_chain_and_releases_lease_without_leaking_payload(env, phase, failure):
    original = env.options[phase]
    def bad(permit, deadline):
        if failure == "exception":
            raise RuntimeError("PRIVATE_CALLBACK_DETAIL")
        result = original(permit, deadline)
        if failure == "permit_copy":
            result["maintenance_permit"] = replace(permit)
        elif failure == "false_ok":
            result["ok"] = False
        else:
            result["synthetic_only"] = False
        return result
    outcome = env.build(**{phase: bad}).run_offline(env.request)
    assert outcome["ok"] is False
    assert "PRIVATE_CALLBACK_DETAIL" not in repr(outcome)
    assert env.lease()["state"] == "RELEASED"
    assert len(env.calls) <= ["bootstrap", "startup_recovery", "postflight"].index(phase) + 1


@pytest.mark.parametrize("field,value", [
    ("prepared_transactions_after", 1), ("resolved_transactions_after", 1),
    ("unresolved_transactions_after", 1), ("unresolved_transactions_after", False),
])
def test_pending_recovery_never_passes_to_postflight(env, field, value):
    def recovery(permit, deadline):
        return env.options["startup_recovery"](permit, deadline) | {field: value}
    result = env.build(startup_recovery=recovery).run_offline(env.request)
    assert result["status"] == "C3_MAINTENANCE_RECOVERY_UNVERIFIED"
    assert env.calls == ["bootstrap", "recovery"]


def test_second_coordinator_cannot_enter_same_physical_lease(env):
    other = env.c.build_production_closed_repair_writer_runtime_coordinator_v1(
        config=env.c.ProductionWriterRuntimeCoordinatorBindingConfigV1(
            enabled=True,
            scope_attestation=env.c.PRODUCTION_COORDINATOR_EXPLICIT_DEPENDENCY_BINDING_ATTESTATION_V1,
            storage_root_binding_sha256=env.options["storage_root_binding_sha256"],
            lock_timeout_seconds=0.01,
        ), lock_backend=env.locks, lease_store=env.leases,
        registry_path=env.registry_path,
        clock=lambda: env.time, nonce_source=lambda: "other-synthetic-nonce",
    )
    def bootstrap(permit, deadline):
        with pytest.raises(env.c.WriterRuntimeCoordinationBlocked, match="SHARED_LOCK_TIMEOUT"):
            with other.maintenance_lease():
                pytest.fail("second lease admitted")
        with pytest.raises(env.c.WriterRuntimeCoordinationBlocked, match="MAINTENANCE_LEASE_ACTIVE"):
            with other.mutation(env.c.canonical_runtime_writer_inventory_v1()[0]["writer_id"]):
                pytest.fail("competing writer admitted")
        return env.options["bootstrap"](permit, deadline)
    assert env.build(bootstrap=bootstrap).run_offline(env.request)["ok"] is True


def test_same_instance_concurrent_request_does_not_start_second_chain(env):
    entered, proceed = threading.Event(), threading.Event()
    result = []
    def bootstrap(permit, deadline):
        entered.set()
        assert proceed.wait(3)
        return env.options["bootstrap"](permit, deadline)
    composition = env.build(bootstrap=bootstrap)
    worker = threading.Thread(target=lambda: result.append(composition.run_offline(env.request)))
    worker.start()
    try:
        assert entered.wait(3)
        assert composition.run_offline(env.request)["status"] == "C3_MAINTENANCE_ATTEMPT_IN_PROGRESS"
    finally:
        proceed.set()
        worker.join(3)
    assert not worker.is_alive()
    assert result[0]["ok"] is True
    assert len(env.bindings) == 1


def test_unresolved_durable_lease_blocks_new_instance(env):
    env.leases.write(env.c.canonical_runtime_lock_namespace_v1(), {
        "state": "QUIESCED", "maintenance_epoch": "a" * 64, "registered_writer_count": 19,
    })
    result = env.build().run_offline(env.request)
    assert result["ok"] is False and env.calls == []
    assert env.lease()["state"] == "QUIESCED"


@pytest.mark.parametrize("fail_state", ["REQUESTED", "DRAINING", "QUIESCED", "RELEASED"])
def test_lease_persistence_failure_never_reports_completion(env, monkeypatch, fail_state):
    original = env.leases.write
    def write(namespace, lease):
        if lease["state"] == fail_state:
            raise OSError("PRIVATE_STORAGE_DETAIL")
        original(namespace, lease)
    monkeypatch.setattr(env.leases, "write", write)
    result = env.build().run_offline(env.request)
    assert result["ok"] is False and "PRIVATE_STORAGE_DETAIL" not in repr(result)
    if fail_state == "RELEASED":
        assert env.lease()["state"] == "QUIESCED"
    else:
        assert env.calls == []


def test_nonce_failure_after_os_lock_acquired_still_releases_lock(env):
    calls = 0
    def nonce():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("synthetic nonce failure")
        return "synthetic"
    result = env.build(nonce_source=nonce).run_offline(env.request)
    assert result["ok"] is False
    handle = env.locks.acquire(env.c.canonical_runtime_lock_namespace_v1(), 0.02)
    assert handle is not None
    handle.release()


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), -1, 0, 301])
def test_invalid_budget_rejected(env, value):
    with pytest.raises(ValueError):
        env.m.MaintenanceActivationConfigV1(max_duration_seconds=value)


def test_maintenance_coordinator_cannot_be_promoted_by_runtime_installer(env, monkeypatch):
    seam = importlib.import_module("trade_registry_closed_identity_conflict_repair_runtime_seam_v1")
    authority, interlock = object(), object()
    monkeypatch.setattr(seam, "_controlled_activation_authority_v1", authority)
    monkeypatch.setattr(seam, "_controlled_activation_interlock_v1", interlock)
    composition = env.build()
    assert composition.run_offline(env.request)["ok"] is True
    with pytest.raises(env.c.WriterRuntimeCoordinationBlocked, match="MAINTENANCE_ONLY_RUNTIME_ACTIVATION_FORBIDDEN"):
        seam.install_controlled_c3_closed_repair_writer_coordinator_v1(
            composition._coordinator, enabled=True,
            scope_attestation=seam.C3_CONTROLLED_RUNTIME_ACTIVATION_SCOPE_ATTESTATION_V1,
            activation_authority=authority, activation_interlock=interlock,
        )


@pytest.mark.parametrize("port", ["clock", "consume_authorization", "kill_switch", "bootstrap", "startup_recovery", "postflight"])
def test_missing_port_prevents_any_execution(env, port):
    result = env.build(**{port: None}).run_offline(env.request)
    assert result["status"] == "C3_MAINTENANCE_DEPENDENCIES_REQUIRED"
    assert env.calls == env.bindings == []


def test_wrong_storage_binding_blocks_before_any_step(env):
    result = env.build(storage_root_binding_sha256="b" * 64).run_offline(env.request)
    assert result["ok"] is False
    assert env.calls == []
    assert env.lease() is None


def test_different_storage_roots_rejected(env, tmp_path):
    leases = env.s.DurableJsonMaintenanceLeaseStoreV1(tmp_path / "other-synthetic", enabled=True)
    result = env.build(lease_store=leases).run_offline(env.request)
    assert result["ok"] is False and env.calls == []


@pytest.mark.parametrize("failure", ["deadline", "kill_switch"])
def test_slow_or_revoked_authorization_cannot_reach_storage(env, failure):
    def authorize(_request, binding):
        if failure == "deadline":
            env.time = binding.deadline
        else:
            env.kill = True
        return True
    result = env.build(consume_authorization=authorize).run_offline(env.request)
    assert result["ok"] is False
    assert env.calls == [] and list(env.root.iterdir()) == []


def test_callback_cannot_leak_details_through_public_exception_class(env):
    def bad(*_):
        raise env.m.MaintenanceActivationBlocked("PRIVATE_CALLBACK_DETAIL")
    result = env.build(bootstrap=bad).run_offline(env.request)
    assert result["status"] == "C3_MAINTENANCE_FAILED_CLOSED"
    assert "PRIVATE" not in repr(result)


def test_kill_switch_initially_engaged_prevents_authorization(env):
    env.kill = True
    result = env.build().run_offline(env.request)
    assert result["status"] == "C3_MAINTENANCE_KILL_SWITCH_ENGAGED"
    assert env.calls == env.bindings == []


def test_success_receipt_requires_release_epoch_match(env, monkeypatch):
    original = env.leases.read
    def read(namespace):
        result = original(namespace)
        if result and result.get("state") == "RELEASED":
            return result | {"maintenance_epoch": "b" * 64}
        return result
    monkeypatch.setattr(env.leases, "read", read)
    result = env.build().run_offline(env.request)
    assert result["status"] == "C3_MAINTENANCE_RELEASE_UNVERIFIED"


def test_offline_module_is_not_automatically_run_by_main(env):
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "main.py").read_text(encoding="utf-8-sig"))
    names = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module)
    assert "trade_registry_c3_maintenance_activation_offline_v1" not in names
    assert not any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run_offline" for node in ast.walk(tree)
    )


def supplied_coordinator(env):
    coordinator = env.c.build_production_closed_repair_writer_runtime_coordinator_v1(
        config=env.c.ProductionWriterRuntimeCoordinatorBindingConfigV1(
            enabled=True, maintenance_only=True,
            scope_attestation=env.c.PRODUCTION_COORDINATOR_EXPLICIT_DEPENDENCY_BINDING_ATTESTATION_V1,
            storage_root_binding_sha256=env.options["storage_root_binding_sha256"],
            lock_timeout_seconds=0.02,
        ), lock_backend=env.locks, lease_store=env.leases,
        registry_path=env.registry_path,
        clock=env.options["clock"], nonce_source=env.options["nonce_source"],
    )
    return coordinator


def test_supplied_coordinator_is_never_rebuilt_and_permit_expires(env, monkeypatch):
    coordinator = supplied_coordinator(env)
    def forbidden(**_):
        pytest.fail("injected coordinator was rebuilt")
    monkeypatch.setattr(env.c, "build_production_closed_repair_writer_runtime_coordinator_v1", forbidden)
    composition = env.build(maintenance_coordinator=coordinator)
    assert composition.run_offline(env.request)["ok"] is True
    assert composition._coordinator is coordinator
    assert coordinator.maintenance_permit_is_current_v1(
        asdict(env.permits[0]), lock_backend=env.locks) is False
    assert coordinator.maintenance_only is True
    assert env.lease()["state"] == "RELEASED"


def test_default_off_does_not_inspect_supplied_coordinator(env):
    class Bomb:
        def __getattribute__(self, _):
            pytest.fail("default-off inspected supplied coordinator")
    outcome = env.build(config=env.m.MaintenanceActivationConfigV1(),
                        maintenance_coordinator=Bomb()).run_offline(env.request)
    assert outcome["status"] == "C3_MAINTENANCE_DEFAULT_OFF"
    assert env.bindings == env.calls == []
    assert list(env.root.iterdir()) == []


@pytest.mark.parametrize("mismatch", [
    "type", "disabled", "not_maintenance", "backend", "store", "root", "clock", "nonce",
    "namespace", "writers", "inflight", "timeout", "nan_timeout", "bool_timeout",
])
def test_supplied_graph_mismatch_denied_before_consumption(env, mismatch):
    coordinator = supplied_coordinator(env)
    overrides = {}
    if mismatch == "type":
        coordinator = object()
    elif mismatch == "disabled":
        coordinator._config = replace(coordinator._config, enabled=False)
    elif mismatch == "not_maintenance":
        coordinator._config = replace(coordinator._config, maintenance_only=False)
    elif mismatch in {"timeout", "nan_timeout", "bool_timeout"}:
        value = {"timeout": 1, "nan_timeout": float("nan"), "bool_timeout": True}[mismatch]
        coordinator._config = replace(coordinator._config, lock_timeout_seconds=value)
    elif mismatch == "backend":
        coordinator._lock_backend = env.s.CrossPlatformInterprocessFileLockBackendV1(env.root, enabled=True)
    elif mismatch == "store":
        coordinator._lease_store = env.s.DurableJsonMaintenanceLeaseStoreV1(env.root, enabled=True)
    elif mismatch == "root":
        overrides["storage_root_binding_sha256"] = "a" * 64
    elif mismatch == "clock":
        coordinator._clock = lambda: env.time
    elif mismatch == "nonce":
        coordinator._nonce_source = lambda: "synthetic-nonce"
    elif mismatch == "namespace":
        coordinator._namespace = "a" * 64
    elif mismatch == "writers":
        coordinator._registered.pop(next(iter(coordinator._registered)))
    elif mismatch == "inflight":
        coordinator._inflight = 1
    outcome = env.build(maintenance_coordinator=coordinator, **overrides).run_offline(env.request)
    assert outcome["status"] == "C3_MAINTENANCE_COORDINATOR_BINDING_INVALID"
    assert env.bindings == env.calls == []
    assert list(env.root.iterdir()) == []


@pytest.mark.parametrize("slot", ["_config", "_lock_backend", "_lease_store", "_clock"])
def test_supplied_graph_rechecked_after_authorization(env, slot):
    coordinator = supplied_coordinator(env)
    def authorize(request, binding):
        assert env.options["consume_authorization"](request, binding)
        original = getattr(coordinator, slot)
        replacement = replace(original) if slot == "_config" else copy.copy(original)
        if slot == "_clock":
            replacement = lambda: env.time
        setattr(coordinator, slot, replacement)
        return True
    outcome = env.build(maintenance_coordinator=coordinator,
                        consume_authorization=authorize).run_offline(env.request)
    assert outcome["status"] == "C3_MAINTENANCE_COORDINATOR_BINDING_INVALID"
    assert len(env.bindings) == 1 and env.calls == []
    assert list(env.root.iterdir()) == []


def test_supplied_lock_budget_must_fit_remaining_deadline(env):
    coordinator = supplied_coordinator(env)
    def authorize(request, binding):
        assert env.options["consume_authorization"](request, binding)
        env.time = binding.deadline - 0.01
        return True
    outcome = env.build(maintenance_coordinator=coordinator,
                        consume_authorization=authorize).run_offline(env.request)
    assert outcome["status"] == "C3_MAINTENANCE_DEADLINE_EXCEEDED"
    assert env.calls == [] and list(env.root.iterdir()) == []


def test_active_supplied_coordinator_rejected_before_consumption(env):
    coordinator = supplied_coordinator(env)
    with coordinator.maintenance_lease():
        outcome = env.build(maintenance_coordinator=coordinator).run_offline(env.request)
        assert outcome["status"] == "C3_MAINTENANCE_COORDINATOR_BINDING_INVALID"
        assert env.calls == env.bindings == []


def test_lost_current_lease_stops_before_recovery(env):
    coordinator = supplied_coordinator(env)
    def bootstrap(permit, deadline):
        result = env.options["bootstrap"](permit, deadline)
        lease = env.lease()
        env.leases.write(coordinator.lock_namespace, lease | {"state": "RELEASED"})
        return result
    result = env.build(maintenance_coordinator=coordinator, bootstrap=bootstrap).run_offline(env.request)
    assert result["status"] == "C3_MAINTENANCE_PERMIT_INVALID"
    assert env.calls == ["bootstrap"]


@pytest.fixture
def recovery_values():
    h = importlib.import_module(
        "trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_harness_v2")
    # The physical reference explicitly requires the system temporary root.
    with tempfile.TemporaryDirectory(prefix="c3_maintenance_chain_") as root:
        yield h.build_authenticated_persistent_authority_production_adapters_context_v2(root)


def recovery_composition_options(
    env, values, *, foreign_coordinator=False, synthetic_registry_write=False,
):
    """Shared synthetic input preparation; does not run maintenance or startup."""
    bridge = values["bridge"]
    original_prepared = values["prepared"]
    seam = importlib.import_module("trade_registry_closed_identity_conflict_repair_runtime_seam_v1")
    identity = importlib.import_module(
        "trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2")
    def prepared(permit):
        # Configure the synthetic input scenario BEFORE the bridge validates it.
        # This fake performs no Registry I/O; never rewrite a verified receipt.
        raw = original_prepared(permit)
        if not synthetic_registry_write:
            raw.update(prepared_transactions_before=0, write_executed=False, registry_write=False)
            raw["startup_recovery_attestation_sha256"] = seam.startup_recovery_attestation_sha256_v1(raw)
        return raw
    bridge._prepared_recovery = prepared
    bridge._config = replace(bridge._config, expected_prepared_recovery_object_identity_sha256=
        identity.startup_recovery_evidence_source_object_identity_sha256_v2(prepared))
    coordinator = values["maintenance_coordinator"]
    used = copy.copy(coordinator) if foreign_coordinator else coordinator
    reports, phases = [], []
    def common(permit):
        return dict(ok=True, maintenance_permit=permit, synthetic_only=True,
                    registry_write=False, no_order_sent=True)
    def bootstrap(permit, deadline):
        phases.append("bootstrap")
        return common(permit) | dict(migration_done=True, restart_readiness_attested=True,
                                    last_load_ok=True, last_write_ok=True, write_allowed=True,
                                    temporary_read_only=False)
    def recovery(permit, deadline):
        phases.append("recovery")
        report = values["boundary"](asdict(permit))
        reports.append(report)
        # Do not override any recovery flags: a write report must remain rejected.
        return report | {"maintenance_permit": permit,
                         "startup_recovery_verified": report.get("startup_bridge_verified") is True}
    def postflight(permit, deadline):
        phases.append("postflight")
        assert reports[-1]["ok"] is True
        return common(permit) | dict(registry_storage_ready=True, startup_recovery_verified=True,
                                    blocking_failures=0, runtime_activation_allowed=False, live_allowed=False)
    options = dict(
        maintenance_coordinator=used,
        config=replace(env.options["config"], lock_timeout_seconds=1),
        lock_backend=values["lock_backend"], lease_store=values["lease_store"],
        storage_root_binding_sha256=env.c.production_coordinator_storage_root_binding_sha256_v1(
            values["lock_backend"].storage_root),
        registry_path=str(values["lock_backend"].storage_root.parent / "synthetic-trade-registry.json"),
        clock=used._clock, nonce_source=used._nonce_source,
        bootstrap=bootstrap, startup_recovery=recovery, postflight=postflight,
    )
    return SimpleNamespace(options=options, reports=reports, phases=phases, used=used, seam=seam)


@pytest.mark.parametrize("foreign_coordinator", [False, True])
@pytest.mark.parametrize("synthetic_registry_write", [False, True])
def test_injected_maintenance_composes_with_existing_recovery_boundary(
    env, recovery_values, foreign_coordinator, synthetic_registry_write,
):
    values = recovery_values
    chain = recovery_composition_options(env, values, foreign_coordinator=foreign_coordinator,
                                        synthetic_registry_write=synthetic_registry_write)
    reports, phases, used, seam = chain.reports, chain.phases, chain.used, chain.seam
    composition = env.build(**chain.options)
    result = composition.run_offline(env.request)
    expected = not foreign_coordinator and not synthetic_registry_write
    assert result["ok"] is expected, (
        result["status"], phases,
        [(r.get("status"), r.get("reason")) for r in reports])
    assert phases == (["bootstrap", "recovery", "postflight"] if expected else ["bootstrap", "recovery"])
    assert values["transaction_port"].call_count == (0 if foreign_coordinator else 1)
    assert values["resolved_port"].call_count == (0 if foreign_coordinator else 1)
    if not foreign_coordinator:
        assert reports[0]["registry_write"] is synthetic_registry_write
        assert reports[0]["startup_recovery_attestation_sha256"] == seam.startup_recovery_attestation_sha256_v1(reports[0])
    assert result["production_ready"] is result["runtime_integrated"] is result["live_allowed"] is False
    assert values["lease_store"].read(used.lock_namespace)["state"] == "RELEASED"
