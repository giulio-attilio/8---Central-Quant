"""Synthetic-only tests; run with the isolated dependency-assembly launcher."""
from dataclasses import replace, FrozenInstanceError
import pytest
import c3_runtime_dependency_assembly_offline_v1 as assembly


class NoCalls:
    """Every protocol is a trap; construction must retain, never invoke it."""
    def __init__(self):
        self.calls = 0

    def __repr__(self):
        raise AssertionError("dependency repr must not be evaluated")

    def __call__(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("offline assembly invoked a dependency")

    acquire = read = write = __enter__ = __exit__ = __call__
    read_current_root_authority_v2 = verify_root_authority_signature_v2 = __call__
    root_authority_key_revoked_v2 = recover_multistore_v2 = __call__


def fixture():
    names = ("atomic_lock", "trading_controls", "startup_state", "seam_binding_evidence",
             "maintenance_completion_evidence", "production_evidence_verifier", "startup_callback")
    port_values = {name: NoCalls() for name in names}
    ports = assembly.ports_v1.RuntimeProductionStartupPortsV1(
        **port_values, synthetic_only=True, runtime_integrated=False)
    dep_names = ("lock_backend", "lease_store", "clock", "nonce_source", "root_state_provider",
                 "root_authority_verifier", "root_revocation_source", "multistore_recovery", "startup_bridge")
    dep_values = {name: NoCalls() for name in dep_names}
    dependencies = assembly.SyntheticAssemblyDependenciesV1(ports=ports, **dep_values)
    return dependencies, tuple(port_values.values()) + tuple(dep_values.values())


def test_exact_bindings_default_off_and_no_global_install():
    d, traps = fixture()
    seam = assembly.seam_v1
    before = (seam._coordinator, seam._controlled_activation_authority_v1,
              seam._controlled_activation_interlock_v1)
    result = assembly.assemble_c3_dependencies_offline_v1(d)
    assert all(getattr(owner, slot) is value for owner, slot, value in result._edges)
    assert result.coordinator.registered_writer_count == 0
    assert result.coordinator.inflight_mutations == 0
    assert result.coordinator is not seam._coordinator
    assert all(a is b for a, b in zip(before, (
        seam._coordinator, seam._controlled_activation_authority_v1,
        seam._controlled_activation_interlock_v1)))
    for _ in range(3):
        snapshot = result.snapshot()
        assert snapshot["ok"] and snapshot["default_off"]
        for flag in ("runtime_integrated", "production_authority", "production_ready",
                     "activation_allowed", "live_allowed", "order_submission_authorized"):
            assert snapshot[flag] is False
    assert all(trap.calls == 0 for trap in traps)


def test_disabled_components_reject_before_any_provider_call():
    d, traps = fixture()
    result = assembly.assemble_c3_dependencies_offline_v1(d)
    denied = result.authority({})
    assert denied["ok"] is False and denied["production_authority"] is False
    with pytest.raises(assembly.gate_v1.RuntimeStartupAdmissionBlocked):
        with result.gate.startup_admission({}):
            pytest.fail("startup was admitted")
    with pytest.raises(assembly.composition_v1.RuntimeProductionStartupCompositionBlocked):
        result.composition.rehearse_offline()
    for operation in (result.interlock.coordination_status,
                      result.interlock.run_startup_recovery_v1):
        with pytest.raises(assembly.coordinator_v1.WriterRuntimeCoordinationBlocked):
            operation()
    with pytest.raises(assembly.coordinator_v1.WriterRuntimeCoordinationBlocked):
        with result.interlock.maintenance_lease():
            pytest.fail("uninstalled interlock issued a maintenance lease")
    assert all(trap.calls == 0 for trap in traps)


@pytest.mark.parametrize("field", ["lock_backend", "lease_store", "clock", "nonce_source",
    "root_state_provider", "root_authority_verifier", "root_revocation_source",
    "multistore_recovery", "startup_bridge"])
def test_missing_dependency_is_rejected(field):
    d, traps = fixture()
    with pytest.raises(assembly.OfflineAssemblyBlocked, match="DEPENDENCY_MISSING"):
        assembly.assemble_c3_dependencies_offline_v1(replace(d, **{field: None}))
    assert all(trap.calls == 0 for trap in traps)


@pytest.mark.parametrize("field", ["atomic_lock", "trading_controls", "startup_state",
    "seam_binding_evidence", "maintenance_completion_evidence",
    "production_evidence_verifier", "startup_callback"])
def test_missing_startup_port_is_rejected(field):
    d, traps = fixture()
    with pytest.raises(assembly.OfflineAssemblyBlocked):
        assembly.assemble_c3_dependencies_offline_v1(
            replace(d, ports=replace(d.ports, **{field: None})))
    assert all(trap.calls == 0 for trap in traps)


@pytest.mark.parametrize("changes", [{"synthetic_only": False}, {"synthetic_only": 1},
    {"runtime_integrated": True}, {"runtime_integrated": 0}, {"authority_root_sha256": "a" * 64}])
def test_production_claims_are_not_accepted(changes):
    d, traps = fixture()
    with pytest.raises(assembly.OfflineAssemblyBlocked):
        assembly.assemble_c3_dependencies_offline_v1(replace(d, ports=replace(d.ports, **changes)))
    assert all(trap.calls == 0 for trap in traps)


def test_exact_dto_and_synthetic_scope_required():
    d, _ = fixture()
    for invalid in (None, {}, replace(d, synthetic_only=False), replace(d, synthetic_only=1)):
        with pytest.raises(assembly.OfflineAssemblyBlocked):
            assembly.assemble_c3_dependencies_offline_v1(invalid)


def test_every_bound_edge_detects_instance_swap():
    d, traps = fixture()
    result = assembly.assemble_c3_dependencies_offline_v1(d)
    # Deliberate tampering, including frozen DTOs: no changed graph may attest OK.
    # The global seam is tested separately without changing it.
    for owner, slot, original in result._edges:
        if owner is assembly.seam_v1:
            continue
        try:
            object.__setattr__(owner, slot, NoCalls())
            assert result.snapshot()["ok"] is False
        finally:
            object.__setattr__(owner, slot, original)
        assert result.snapshot()["ok"] is True
    assert all(trap.calls == 0 for trap in traps)


@pytest.mark.parametrize("component", ["coordinator", "authority", "gate", "composition"])
def test_config_replacement_and_enabled_drift_fail_closed(component):
    d, traps = fixture()
    result = assembly.assemble_c3_dependencies_offline_v1(d)
    owner = getattr(result, component)
    original = owner._config
    for enabled in (False, True, 1):
        owner._config = replace(original, enabled=enabled)
        assert result.snapshot()["ok"] is False
        assert result.snapshot()["default_off"] is False
    owner._config = original
    assert result.snapshot()["ok"] is True
    assert all(trap.calls == 0 for trap in traps)


def test_representations_protected_and_result_frozen():
    d, traps = fixture()
    result = assembly.assemble_c3_dependencies_offline_v1(d)
    assert repr(d) == "<SyntheticAssemblyDependenciesV1 protected>"
    assert repr(result) == "<DormantOfflineAssemblyV1 protected>"
    with pytest.raises(FrozenInstanceError):
        result.gate = None
    assert all(trap.calls == 0 for trap in traps)


def test_existing_production_adapter_still_rejects_synthetic_ports():
    d, traps = fixture()
    p = assembly.ports_v1
    config = p.RuntimeProductionStartupPortBindingAdapterConfigV1(
        scope_attestation=p.RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_SCOPE_ATTESTATION_V1,
        expected_ports_identity_sha256=p.runtime_production_startup_ports_identity_sha256_v1(d.ports))
    adapter = p.RuntimeProductionStartupPortBindingAdapterContractV1(ports=d.ports, config=config)
    assert adapter.snapshot()["reason"] == "C3_RUNTIME_PRODUCTION_STARTUP_PORTS_SYNTHETIC_FORBIDDEN"
    with pytest.raises(p.RuntimeProductionStartupPortBindingBlocked):
        adapter.bind_dormant()
    assert all(trap.calls == 0 for trap in traps)
