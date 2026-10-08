"""Exercise only reviewed AST fragments: main is data, never an imported app."""
import ast
import builtins
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from threading import RLock

import pytest
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2 as adapters_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_v2 as boundary_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_port_binding_adapter_contract_v1 as ports_v1
import trade_registry_closed_identity_conflict_repair_runtime_static_preflight_v1 as static_v1


def forbidden(*args, **kwargs):
    raise AssertionError("dormant startup must not perform I/O or invoke providers")


@pytest.fixture
def tree():
    return ast.parse((Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8"))


@pytest.fixture
def no_io(monkeypatch):
    # Dependencies and source have already been loaded; construction gets no I/O.
    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(Path, "resolve", forbidden)
        patch.setattr(Path, "mkdir", forbidden)
        patch.setattr(coordinator_v1._DenyLockBackend, "acquire", forbidden)
        patch.setattr(coordinator_v1._DenyLeaseStore, "read", forbidden)
        patch.setattr(coordinator_v1._DenyLeaseStore, "write", forbidden)
        yield


def define(tree, name, namespace):
    namespace.setdefault("__name__", "synthetic_dormant_startup_fragments")
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<reviewed-startup-fragment>", "exec"), namespace)
    return namespace[name]


def namespace():
    return {
        "c3_writer_coordinator_v1": coordinator_v1,
        "c3_authenticated_persistent_authority_production_adapters_v2": adapters_v2,
        "c3_authenticated_persistent_authority_boundary_v2": boundary_v2,
    }


def build_graph():
    coordinator = coordinator_v1.build_production_closed_repair_writer_runtime_coordinator_v1()
    adapters = adapters_v2.build_dormant_authenticated_persistent_authority_production_adapters_v2(
        maintenance_coordinator=coordinator)
    boundary = boundary_v2.build_dormant_authenticated_persistent_authority_boundary_v2(
        root_state_provider=adapters.root_state_provider,
        root_authority_verifier=adapters.root_authority_verifier,
        root_revocation_source=adapters.root_revocation_source,
        multistore_recovery=adapters.multistore_recovery,
        startup_bridge=forbidden)
    return coordinator, adapters, boundary


def test_actual_startup_assignments_share_one_instance_without_io(tree, no_io):
    ns = namespace()
    ns["C3_CLOSED_REPAIR_RESOLVED_AUTHORITY_STARTUP_BRIDGE_V2"] = forbidden
    names = {
        "C3_CLOSED_REPAIR_WRITER_COORDINATOR_DORMANT_V1",
        "C3_CLOSED_REPAIR_AUTHENTICATED_PERSISTENT_AUTHORITY_PRODUCTION_ADAPTERS_V2",
        "C3_CLOSED_REPAIR_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_V2",
    }
    selected = [n for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    assert len(selected) == 3
    exec(compile(ast.Module(body=selected, type_ignores=[]), "<reviewed-startup-assignments>", "exec"), ns)
    coordinator = ns["C3_CLOSED_REPAIR_WRITER_COORDINATOR_DORMANT_V1"]
    recovery = ns["C3_CLOSED_REPAIR_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_V2"]
    adapter = ns["C3_CLOSED_REPAIR_AUTHENTICATED_PERSISTENT_AUTHORITY_PRODUCTION_ADAPTERS_V2"]
    assert recovery._multistore_recovery is adapter.multistore_recovery
    assert adapter.multistore_recovery.dormant_coordinator_bound_v2(coordinator)
    assert coordinator.registered_writer_count == 0
    assert coordinator.enabled is False
    assert adapter.multistore_recovery._lock_backend is None
    assert adapter.multistore_recovery._transaction_recovery is None
    assert adapter.multistore_recovery._resolved_recovery is None
    assert adapter.snapshot()["production_ready"] is False
    assert recovery({})["ok"] is False
    with pytest.raises(RuntimeError, match="COORDINATED_MULTISTORE_RECOVERY_NOT_READY"):
        adapter.multistore_recovery.recover_multistore_v2(
            maintenance_permit={}, root_authority_attestation={}, now_epoch=1)


def test_active_registry_path_from_main_is_accepted_only_with_colocated_coordination(tree, tmp_path):
    # Execute only the path resolver AST, never import or start main.py.
    active_file = define(tree, "_trpsf_v1_active_file", {
        "Path": Path, "CENTRAL_DATA_DIR": tmp_path,
    })()
    assert active_file == tmp_path / "trade_registry.json"
    storage = coordinator_v1.runtime_storage
    root = tmp_path / "c3-coordination"
    locks = storage.CrossPlatformInterprocessFileLockBackendV1(root, enabled=True)
    leases = storage.DurableJsonMaintenanceLeaseStoreV1(root, enabled=True)
    binding = coordinator_v1.ProductionWriterRuntimeCoordinatorBindingConfigV1(
        enabled=True,
        scope_attestation=coordinator_v1.PRODUCTION_COORDINATOR_EXPLICIT_DEPENDENCY_BINDING_ATTESTATION_V1,
        storage_root_binding_sha256=coordinator_v1.production_coordinator_storage_root_binding_sha256_v1(root),
        maintenance_only=True,
    )
    def build(path):
        return coordinator_v1.build_production_closed_repair_writer_runtime_coordinator_v1(
            config=binding, lock_backend=locks, lease_store=leases,
            registry_path=path, clock=lambda: 1.0, nonce_source=lambda: "synthetic-nonce",
        )
    assert build(active_file)._registry_path_binding == active_file.resolve()
    with pytest.raises(coordinator_v1.WriterRuntimeCoordinationBlocked,
                       match="PRODUCTION_COORDINATOR_REGISTRY_STORAGE_BINDING_INVALID"):
        build(tmp_path / "other" / "trade_registry.json")
    assert not active_file.exists()


def installer_namespace():
    ns, calls = namespace(), []
    def install(coordinator):
        calls.append(("install", coordinator))
        return {"enabled": False}
    def bind(coordinator, *, startup_recovery):
        calls.append(("bind", coordinator, startup_recovery))
        return SimpleNamespace(coordinator=coordinator, recovery=startup_recovery)
    def capability():
        calls.append(("capability",))
        return SimpleNamespace(snapshot=lambda: {"enabled": False})
    ns.update({
        "c3_runtime_seam_v1": SimpleNamespace(
            install_dormant_c3_closed_repair_writer_coordinator_v1=install,
            bind_c3_closed_repair_runtime_interlocks_v1=bind),
        "c3_writer_invocation_v1": SimpleNamespace(build_production_writer_invocation_adapter_v1=capability),
        "c3_transaction_store_v1": SimpleNamespace(build_production_raw_transaction_store_v1=capability),
        "c3_provider_v1": SimpleNamespace(build_production_closed_repair_provider_v1=capability),
        "_C3_CLOSED_REPAIR_RUNTIME_INTERLOCKS_V1": None,
    })
    return ns, calls


def test_installer_passes_same_instance_to_both_interlocks(tree, no_io):
    ns, calls = installer_namespace()
    installer = define(tree, "_install_c3_closed_repair_writer_coordination_v1", ns)
    coordinator, _, recovery = build_graph()
    result = installer(coordinator=coordinator, startup_recovery=recovery)
    assert result["ok"] and result["enabled"] is False
    assert result["coordination_ready"] is False
    assert result["runtime_activation_allowed"] is False
    assert calls[-2:] == [("install", coordinator), ("bind", coordinator, recovery)]
    bound = ns["_C3_CLOSED_REPAIR_RUNTIME_INTERLOCKS_V1"]
    assert bound.coordinator is coordinator and bound.recovery is recovery


@pytest.mark.parametrize("drift", ["coordinator", "enabled", "pin", "adapter_enabled", "boundary_enabled", "missing"])
def test_installer_refuses_graph_drift_before_any_install(tree, no_io, drift):
    ns, calls = installer_namespace()
    installer = define(tree, "_install_c3_closed_repair_writer_coordination_v1", ns)
    coordinator, adapters, recovery = build_graph()
    if drift == "coordinator":
        coordinator = coordinator_v1.build_production_closed_repair_writer_runtime_coordinator_v1()
    elif drift == "enabled":
        coordinator._config = replace(coordinator._config, enabled=True)
    elif drift == "pin":
        adapters.multistore_recovery._config = replace(
            adapters.multistore_recovery._config, expected_maintenance_coordinator_object_identity_sha256="0" * 64)
    elif drift == "adapter_enabled":
        adapters.multistore_recovery._config = replace(adapters.multistore_recovery._config, enabled=True)
    elif drift == "boundary_enabled":
        recovery._config = replace(recovery._config, enabled=True)
    else:
        recovery = None
    with pytest.raises(RuntimeError, match="C3_DORMANT_STARTUP_COORDINATOR_BINDING_REQUIRED"):
        installer(coordinator=coordinator, startup_recovery=recovery)
    assert calls == []
    assert ns["_C3_CLOSED_REPAIR_RUNTIME_INTERLOCKS_V1"] is None


@pytest.mark.parametrize("invalid", ["foreign", "enabled"])
def test_factory_rejects_non_dormant_coordinator(no_io, invalid):
    coordinator = coordinator_v1.build_production_closed_repair_writer_runtime_coordinator_v1()
    if invalid == "foreign":
        coordinator = object()
    else:
        coordinator._config = replace(coordinator._config, enabled=True)
    with pytest.raises(RuntimeError, match="DORMANT_MAINTENANCE_COORDINATOR_REQUIRED"):
        adapters_v2.build_dormant_authenticated_persistent_authority_production_adapters_v2(
            maintenance_coordinator=coordinator)


def test_legacy_no_argument_factory_stays_unbound_and_disabled(no_io):
    adapters = adapters_v2.build_dormant_authenticated_persistent_authority_production_adapters_v2()
    assert adapters.multistore_recovery._maintenance_coordinator is None
    assert adapters.multistore_recovery._config.enabled is False


def test_main_passes_explicit_coordinator_to_installer(tree):
    assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "C3_CLOSED_REPAIR_INSTALLATION_V1" for t in n.targets))
    arguments = {k.arg: k.value for k in assignment.value.keywords}
    assert arguments["coordinator"].id == "C3_CLOSED_REPAIR_WRITER_COORDINATOR_DORMANT_V1"
    assert arguments["startup_recovery"].id == "C3_CLOSED_REPAIR_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_V2"


def test_static_validator_recognizes_explicit_graph(tree):
    assert static_v1._dormant_coordinator_startup_binding(tree) is True


@pytest.mark.parametrize("drift", ["other_instance", "missing_argument", "duplicate_assignment",
                                   "enabled_builder", "guard_removed", "call_before_guard"])
def test_static_validator_rejects_broken_graph(tree, drift):
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "_install_c3_closed_repair_writer_coordination_v1")
    assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "C3_CLOSED_REPAIR_WRITER_COORDINATOR_DORMANT_V1" for t in n.targets))
    if drift in {"other_instance", "missing_argument"}:
        target = next(n for n in tree.body if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "C3_CLOSED_REPAIR_INSTALLATION_V1" for t in n.targets))
        if drift == "missing_argument":
            target.value.keywords = [k for k in target.value.keywords if k.arg != "coordinator"]
        else:
            next(k for k in target.value.keywords if k.arg == "coordinator").value = ast.Name(id="other", ctx=ast.Load())
    elif drift == "duplicate_assignment":
        tree.body.append(assignment)
    elif drift == "enabled_builder":
        assignment.value.keywords.append(ast.keyword(arg="config", value=ast.Name(id="enabled_config", ctx=ast.Load())))
    elif drift == "guard_removed":
        function.body = [n for n in function.body if not isinstance(n, ast.If)]
    else:
        function.body.insert(0, ast.Expr(value=ast.Call(func=ast.Name(id="invoke_provider", ctx=ast.Load()), args=[], keywords=[])))
    assert static_v1._dormant_coordinator_startup_binding(tree) is False


def test_main_gate_uses_corrected_verifier_pin_and_stays_disabled(tree, no_io):
    ns = {
        "c3_runtime_seam_v1": SimpleNamespace(C3_PREBOOTSTRAP_SEAM_CAS_SURFACE_V1=SimpleNamespace(atomic_lock=RLock())),
        "c3_production_startup_port_binding_v1": ports_v1,
        "_c3_closed_identity_repair_trading_controls_v1": forbidden,
    }
    for name in ("state", "seam_binding", "maintenance_completion", "evidence_verifier", "startup_callback"):
        key = {"state": "startup_state", "seam_binding": "seam_binding",
               "maintenance_completion": "maintenance_completion", "evidence_verifier": "evidence_verifier",
               "startup_callback": "startup_callback"}[name]
        define(tree, f"_c3_production_{key}_source_dormant_v1", ns)
    install = define(tree, "_install_c3_production_startup_port_binding_dormant_v1", ns)
    result = install()
    assert result["ok"] and result["activation_possible"] is False, result
    binding = ns["_C3_PRODUCTION_STARTUP_PORT_BINDING_V1"]
    gate = binding.gate
    verifier = ns["_c3_production_evidence_verifier_source_dormant_v1"]
    assert gate._config.expected_verifier_identity_sha256 == ports_v1.gate_contract.production_evidence_verifier_identity_sha256_v1(verifier)
    with pytest.raises(ports_v1.gate_contract.RuntimeStartupAdmissionBlocked):
        with gate.startup_admission({}):
            forbidden()
    with pytest.raises(ports_v1.composition_contract.RuntimeProductionStartupCompositionBlocked):
        binding.composition.rehearse_offline()
