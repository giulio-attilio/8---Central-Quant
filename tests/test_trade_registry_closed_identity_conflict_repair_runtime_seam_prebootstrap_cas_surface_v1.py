from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_prebootstrap_physical_coordinator_port_adapter_harness_v1 as physical_harness
import trade_registry_closed_identity_conflict_repair_prebootstrap_real_seam_cas_adapter_contract_v1 as adapter_contract
import trade_registry_closed_identity_conflict_repair_runtime_seam_v1 as seam
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module


def _enabled_surface(*, synthetic_only: bool = True, runtime_integrated: bool = False):
    return seam.C3PrebootstrapSeamCasSurfaceV1(
        seam.C3PrebootstrapSeamCasSurfaceConfigV1(
            enabled=True,
            scope_attestation=seam.C3_PREBOOTSTRAP_SEAM_CAS_SURFACE_SCOPE_ATTESTATION_V1,
            synthetic_only=synthetic_only,
            runtime_integrated=runtime_integrated,
        )
    )


@pytest.fixture
def isolated_seam_state():
    with seam._prebootstrap_seam_atomic_lock:
        previous_coordinator = seam._coordinator
        previous_guard = seam._prebootstrap_writer_guard
        seam._prebootstrap_writer_guard = None
        seam._coordinator = (
            coordinator_module.build_closed_repair_writer_runtime_coordinator_v1()
        )
    try:
        yield
    finally:
        with seam._prebootstrap_seam_atomic_lock:
            seam._coordinator = previous_coordinator
            seam._prebootstrap_writer_guard = previous_guard


def test_runtime_visible_surface_is_dormant_default_off():
    surface = seam.C3_PREBOOTSTRAP_SEAM_CAS_SURFACE_V1
    status = surface.snapshot()
    assert status["default_off"] is True
    assert status["enabled"] is False
    assert status["production_ready"] is False
    assert status["live_allowed"] is False
    assert status["runtime_activation_allowed"] is False
    assert status["real_registry_accessed"] is False
    assert status["no_order_sent"] is True


def test_default_off_surface_cannot_read_or_replace_coordinator(isolated_seam_state):
    surface = seam.build_dormant_c3_prebootstrap_seam_cas_surface_v1()
    current = seam._coordinator
    with pytest.raises(
        coordinator_module.WriterRuntimeCoordinationBlocked,
        match="C3_PREBOOTSTRAP_SEAM_CAS_SURFACE_DEFAULT_OFF",
    ):
        surface.current_coordinator()
    with pytest.raises(coordinator_module.WriterRuntimeCoordinationBlocked):
        surface.compare_and_swap_coordinator(
            expected_coordinator=current,
            replacement_coordinator=(
                coordinator_module.build_closed_repair_writer_runtime_coordinator_v1()
            ),
        )
    assert seam._coordinator is current


def test_surface_repr_and_config_protect_scope():
    config = seam.C3PrebootstrapSeamCasSurfaceConfigV1(
        enabled=True,
        scope_attestation="hidden-scope",
    )
    assert "hidden-scope" not in repr(config)
    assert repr(seam.C3PrebootstrapSeamCasSurfaceV1(config)) == (
        "<C3PrebootstrapSeamCasSurfaceV1 protected>"
    )


def test_enabled_surface_uses_exact_module_and_atomic_lock(isolated_seam_state):
    surface = _enabled_surface()
    assert surface.module_name == (
        "trade_registry_closed_identity_conflict_repair_runtime_seam_v1"
    )
    assert surface.atomic_lock is seam._prebootstrap_seam_atomic_lock
    assert surface.current_coordinator() is seam._coordinator


def test_coordinator_cas_is_identity_bound_and_self_hashed(isolated_seam_state):
    surface = _enabled_surface()
    before = surface.current_coordinator()
    replacement = coordinator_module.build_closed_repair_writer_runtime_coordinator_v1()
    receipt = surface.compare_and_swap_coordinator(
        expected_coordinator=before,
        replacement_coordinator=replacement,
    )
    assert surface.current_coordinator() is replacement
    supplied = receipt.pop("receipt_sha256")
    assert supplied == hashlib.sha256(
        seam._canonical_json(receipt).encode("utf-8")
    ).hexdigest()
    assert receipt["write_executed"] is False
    assert receipt["registry_write"] is False


def test_coordinator_cas_rejects_stale_identity(isolated_seam_state):
    surface = _enabled_surface()
    current = surface.current_coordinator()
    with pytest.raises(
        coordinator_module.WriterRuntimeCoordinationBlocked,
        match="COORDINATOR_IDENTITY_MISMATCH",
    ):
        surface.compare_and_swap_coordinator(
            expected_coordinator=object(),
            replacement_coordinator=(
                coordinator_module.build_closed_repair_writer_runtime_coordinator_v1()
            ),
        )
    assert surface.current_coordinator() is current


def test_writer_guard_cas_requires_same_atomic_lock(isolated_seam_state):
    surface = _enabled_surface()
    with pytest.raises(
        coordinator_module.WriterRuntimeCoordinationBlocked,
        match="ATOMIC_LOCK_IDENTITY_MISMATCH",
    ):
        surface.compare_and_swap_writer_guard(
            expected_guard=None,
            replacement_guard=lambda _writer_id: {},
            atomic_lock=object(),
        )
    assert surface.current_writer_guard() is None


def test_writer_guard_cas_is_exact_and_covers_inventory(isolated_seam_state):
    surface = _enabled_surface()

    def guard(writer_id: str):
        return {
            "ok": True,
            "writer_id": writer_id,
            "runtime_activation_allowed": False,
        }

    receipt = surface.compare_and_swap_writer_guard(
        expected_guard=None,
        replacement_guard=guard,
        atomic_lock=surface.atomic_lock,
    )
    assert surface.current_writer_guard() is guard
    assert receipt["registered_writer_count"] == 19
    assert receipt["all_writers_routed"] is True
    assert receipt["dynamic_at_invocation"] is True
    assert receipt["same_atomic_lock"] is True


def test_dynamic_writer_guard_blocks_decorated_writer(isolated_seam_state):
    surface = _enabled_surface()

    def blocked(_writer_id: str):
        raise RuntimeError("synthetic maintenance block")

    surface.compare_and_swap_writer_guard(
        expected_guard=None,
        replacement_guard=blocked,
        atomic_lock=surface.atomic_lock,
    )
    with pytest.raises(
        coordinator_module.WriterRuntimeCoordinationBlocked,
        match="C3_PREBOOTSTRAP_SEAM_WRITER_GUARD_BLOCKED",
    ):
        with seam._c3_closed_repair_writer_mutation_v1(
            "TRADE_REGISTRY_UPDATE_OPEN_TRADE"
        ):
            pass


def test_dynamic_writer_guard_accepts_attested_writer(isolated_seam_state):
    surface = _enabled_surface()

    def allowed(writer_id: str):
        return {
            "ok": True,
            "writer_id": writer_id,
            "runtime_activation_allowed": False,
        }

    surface.compare_and_swap_writer_guard(
        expected_guard=None,
        replacement_guard=allowed,
        atomic_lock=surface.atomic_lock,
    )
    with seam._c3_closed_repair_writer_mutation_v1(
        "TRADE_REGISTRY_UPDATE_OPEN_TRADE"
    ) as permit:
        assert permit.admitted is True
        assert permit.coordinated is False


def test_invalid_writer_guard_result_fails_closed(isolated_seam_state):
    surface = _enabled_surface()
    guard = lambda writer_id: {"ok": True, "writer_id": writer_id}
    surface.compare_and_swap_writer_guard(
        expected_guard=None,
        replacement_guard=guard,
        atomic_lock=surface.atomic_lock,
    )
    with pytest.raises(
        coordinator_module.WriterRuntimeCoordinationBlocked,
        match="WRITER_GUARD_ATTESTATION_INVALID",
    ):
        with seam._c3_closed_repair_writer_mutation_v1(
            "TRADE_REGISTRY_UPDATE_OPEN_TRADE"
        ):
            pass


def test_dormant_install_uses_same_lock_and_preserves_bound_guard(isolated_seam_state):
    surface = _enabled_surface()

    def guard(writer_id: str):
        return {
            "ok": True,
            "writer_id": writer_id,
            "runtime_activation_allowed": False,
        }

    surface.compare_and_swap_writer_guard(
        expected_guard=None,
        replacement_guard=guard,
        atomic_lock=surface.atomic_lock,
    )
    replacement = coordinator_module.build_closed_repair_writer_runtime_coordinator_v1()
    seam.install_dormant_c3_closed_repair_writer_coordinator_v1(replacement)
    assert surface.current_coordinator() is replacement
    assert surface.current_writer_guard() is guard


def test_surface_has_no_registry_network_or_live_authority(isolated_seam_state):
    status = _enabled_surface().snapshot()
    assert status["production_ready"] is False
    assert status["live_allowed"] is False
    assert status["runtime_activation_allowed"] is False
    assert status["real_registry_accessed"] is False
    assert status["network_accessed"] is False
    assert status["broker_called"] is False
    assert status["no_order_sent"] is True


def test_offline_adapter_binds_directly_to_real_seam_surface(isolated_seam_state):
    values = physical_harness.build_synthetic_physical_coordinator_composition_v1()
    maintenance = values[4].coordinator
    dormant = seam._coordinator
    surface = _enabled_surface()
    boot_sha = hashlib.sha256(b"real-seam-offline-binding-test").hexdigest()
    adapter = adapter_contract.PrebootstrapRealSeamCasAdapterContractV1(
        seam_surface=surface,
        dormant_coordinator=dormant,
        maintenance_coordinator=maintenance,
        runtime_state=lambda: {
            "runtime_started": False,
            "workers_started": False,
            "server_accepting_requests": False,
        },
        config=adapter_contract.PrebootstrapRealSeamCasAdapterConfigV1(
            enabled=True,
            scope_attestation=adapter_contract.PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_SCOPE_ATTESTATION_V1,
            process_boot_epoch_sha256=boot_sha,
        ),
    )
    binding = adapter.bind_offline()
    state = binding.port.snapshot_installation_state()
    installed = binding.port.compare_and_swap_coordinator(
        expected_generation=state["generation"],
        expected_coordinator=dormant,
        replacement_coordinator=maintenance,
        replacement_mode="MAINTENANCE_ONLY",
    )
    binding.port.compare_and_swap_coordinator(
        expected_generation=installed["generation_after"],
        expected_coordinator=maintenance,
        replacement_coordinator=dormant,
        replacement_mode="DORMANT",
    )
    assert surface.current_coordinator() is dormant
    assert surface.current_writer_guard() is binding.writer_guard


def test_runtime_main_references_only_dormant_cas_surface_lock_without_enabling_it():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(
        encoding="utf-8"
    )
    assert "C3_PREBOOTSTRAP_SEAM_CAS_SURFACE_V1" in source
    assert "C3PrebootstrapSeamCasSurfaceConfigV1" not in source
    assert "C3_PREBOOTSTRAP_SEAM_CAS_SURFACE_SCOPE_ATTESTATION_V1" not in source
