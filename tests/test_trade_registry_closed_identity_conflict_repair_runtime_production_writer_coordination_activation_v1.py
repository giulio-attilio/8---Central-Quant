from __future__ import annotations

import ast
import hashlib
import socket
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_production_writer_coordination_activation_v1 as activation
import trade_registry_closed_identity_conflict_repair_runtime_seam_v1 as seam
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module
import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as storage_module


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolated_seam_and_no_network(monkeypatch):
    previous_coordinator = seam._coordinator
    previous_authority = seam._controlled_activation_authority_v1
    previous_interlock = seam._controlled_activation_interlock_v1
    previous_state = dict(seam._controlled_activation_state)
    seam.install_dormant_c3_closed_repair_writer_coordinator_v1(
        coordinator_module.build_closed_repair_writer_runtime_coordinator_v1()
    )
    monkeypatch.setattr(seam, "_controlled_activation_authority_v1", None)
    monkeypatch.setattr(seam, "_controlled_activation_interlock_v1", None)

    def blocked(*_args, **_kwargs):
        raise AssertionError("network access is forbidden in this test")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    # Windows cannot fsync a directory handle. Storage-adapter durability has
    # its own focused tests; this suite verifies the activation orchestration.
    monkeypatch.setattr(storage_module, "_strict_directory_fsync", lambda _path: None)
    yield
    with seam._prebootstrap_seam_atomic_lock:
        seam._coordinator = previous_coordinator
        seam._controlled_activation_authority_v1 = previous_authority
        seam._controlled_activation_interlock_v1 = previous_interlock
        seam._controlled_activation_state.clear()
        seam._controlled_activation_state.update(previous_state)


def _runtime_stopped() -> dict[str, bool]:
    return {
        "runtime_started": False,
        "workers_started": False,
        "server_accepting_requests": False,
    }


def _activation_evidence(storage_binding: str) -> dict:
    source_files = (
        "trade_registry.py",
        "main.py",
        "bots/meme.py",
        "bots/predator.py",
        "bots/turtle.py",
        "trade_registry_closed_identity_conflict_repair_raw_transaction_store_production_v1.py",
        "trade_registry_closed_identity_conflict_repair_writer_invocation_adapter_v1.py",
        "trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1.py",
        "trade_registry_closed_identity_conflict_repair_production_provider_v1.py",
    )
    evidence = {
        "activation_requested": True,
        "activation_receipt_sha256": "a" * 64,
        "activation_receipt_verified": True,
        "source_hashes_verified": True,
        "source_hashes": {
            name: hashlib.sha256(name.encode("utf-8")).hexdigest()
            for name in source_files
        },
        "shared_lock_backend_ready": True,
        "maintenance_lease_store_ready": True,
        "registry_interlock_ready": True,
        "registry_interlock": {
            "migration_done": True,
            "restart_readiness_attested": True,
            "last_load_ok": True,
            "last_write_ok": True,
            "write_allowed": True,
            "temporary_read_only": False,
        },
        "rollback_ready": True,
        "kill_switch_ready": True,
        "activation_window": {
            "max_duration_seconds": 120.0,
            "rollback_deadline_seconds": 30.0,
            "max_inflight_mutations_before_activation": 0,
            "fail_closed": True,
            "auto_rollback_on_failure": True,
        },
        "trading_controls": {
            "enable_real_trading": False,
            "broker_dry_run": True,
            "falcon_mode": "VERIFY",
            "central_real_execution_enabled": False,
            "central_real_pilot_enabled": False,
            "live_trading_enabled": False,
            "order_submission_authorized": False,
        },
        "storage_root_binding_sha256": storage_binding,
    }
    evidence["activation_evidence_sha256"] = (
        seam.controlled_activation_evidence_sha256_v1(evidence)
    )
    return evidence


def _startup_recovery(permit: dict) -> dict:
    result = {
        "ok": True,
        "wal_inspected": True,
        "transaction_log_inspected": True,
        "prepared_transactions_inspected": True,
        "resolved_transactions_inspected": True,
        "prepared_transactions_before": 0,
        "resolved_transactions_before": 0,
        "prepared_transactions_after": 0,
        "resolved_transactions_after": 0,
        "unresolved_transactions_after": 0,
        "recovery_completed": True,
        "reconciliation_completed": True,
        "maintenance_epoch": permit["maintenance_epoch"],
        "lock_namespace_sha256": permit["lock_namespace_sha256"],
        "filesystem_accessed": True,
        "real_registry_accessed": False,
        "write_executed": False,
        "registry_write": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
        "synthetic_only": False,
        "temporary_storage_only": False,
        "production_authority": True,
        "production_ready": True,
        "runtime_integrated": True,
    }
    result["startup_recovery_attestation_sha256"] = (
        seam.startup_recovery_attestation_sha256_v1(result)
    )
    return result


def _inputs(tmp_path: Path) -> dict:
    storage_root = tmp_path / "coordination"
    binding = (
        coordinator_module.production_coordinator_storage_root_binding_sha256_v1(
            storage_root
        )
    )
    return {
        "storage_root": storage_root,
        "activation_evidence": _activation_evidence(binding),
        "kill_switch": lambda: False,
        "activation_authority": object(),
        "activation_interlock": object(),
        "startup_recovery": _startup_recovery,
        "runtime_state": _runtime_stopped,
        "clock": lambda: 100.0,
        "nonce_source": lambda: "offline-test-nonce",
        "config": activation.ProductionWriterCoordinationActivationConfigV1(
            enabled=True,
            scope_attestation=(
                activation.PRODUCTION_WRITER_COORDINATION_ACTIVATION_SCOPE_ATTESTATION_V1
            ),
            expected_storage_root_binding_sha256=binding,
        ),
    }


def test_default_off_does_not_create_storage(tmp_path: Path) -> None:
    storage_root = tmp_path / "absent"
    with pytest.raises(
        activation.ProductionWriterCoordinationActivationBlocked,
        match="DEFAULT_OFF",
    ):
        activation.activate_production_writer_coordination_v1(
            storage_root=storage_root,
            activation_evidence={},
            kill_switch=lambda: False,
            activation_authority=object(),
            activation_interlock=object(),
            startup_recovery=_startup_recovery,
            runtime_state=_runtime_stopped,
            clock=lambda: 1.0,
            nonce_source=lambda: "nonce",
        )
    assert storage_root.exists() is False
    assert seam.c3_closed_repair_writer_coordination_status_v1()["enabled"] is False


def test_runtime_must_be_stopped_before_storage_is_created(tmp_path: Path) -> None:
    values = _inputs(tmp_path)
    values["runtime_state"] = lambda: {
        "runtime_started": True,
        "workers_started": False,
        "server_accepting_requests": False,
    }
    with pytest.raises(
        activation.ProductionWriterCoordinationActivationBlocked,
        match="PRE_RUNTIME_REQUIRED",
    ):
        activation.activate_production_writer_coordination_v1(**values)
    assert values["storage_root"].exists() is False


def test_complete_activation_coordinates_exact_19_writers(tmp_path: Path) -> None:
    result = activation.activate_production_writer_coordination_v1(
        **_inputs(tmp_path)
    )
    receipt = result.snapshot()
    status = result.interlocks.coordination_status()

    assert receipt["status"] == "C3_PRODUCTION_WRITER_COORDINATION_READY"
    assert receipt["registered_writer_count"] == 19
    assert receipt["all_writers_registered"] is True
    assert receipt["coordination_ready"] is True
    assert receipt["live_allowed"] is False
    assert receipt["order_submission_authorized"] is False
    assert receipt["network_accessed"] is False
    assert receipt["no_order_sent"] is True
    assert status["coordination_ready"] is True
    assert status["startup_recovery_verified"] is True


def test_invalid_startup_recovery_rolls_back_to_dormant(tmp_path: Path) -> None:
    values = _inputs(tmp_path)
    values["startup_recovery"] = lambda _permit: {"ok": False}

    with pytest.raises(
        activation.ProductionWriterCoordinationActivationBlocked,
        match="C3_STARTUP_RECOVERY_ATTESTATION_INVALID",
    ):
        activation.activate_production_writer_coordination_v1(**values)

    status = seam.c3_closed_repair_writer_coordination_status_v1()
    assert status["enabled"] is False
    assert status["coordination_ready"] is False
    assert status["runtime_activation_allowed"] is False


def test_capabilities_are_identity_pinned_and_not_replaceable() -> None:
    authority = object()
    interlock = object()
    first = seam.bind_controlled_c3_runtime_activation_capabilities_v1(
        enabled=True,
        scope_attestation=(
            seam.C3_CONTROLLED_RUNTIME_CAPABILITY_BINDING_SCOPE_ATTESTATION_V1
        ),
        activation_authority=authority,
        activation_interlock=interlock,
    )
    second = seam.bind_controlled_c3_runtime_activation_capabilities_v1(
        enabled=True,
        scope_attestation=(
            seam.C3_CONTROLLED_RUNTIME_CAPABILITY_BINDING_SCOPE_ATTESTATION_V1
        ),
        activation_authority=authority,
        activation_interlock=interlock,
    )
    assert first["status"] == "C3_CONTROLLED_CAPABILITIES_BOUND"
    assert second["status"] == "C3_CONTROLLED_CAPABILITIES_ALREADY_BOUND"
    with pytest.raises(
        coordinator_module.WriterRuntimeCoordinationBlocked,
        match="REPLACEMENT_FORBIDDEN",
    ):
        seam.bind_controlled_c3_runtime_activation_capabilities_v1(
            enabled=True,
            scope_attestation=(
                seam.C3_CONTROLLED_RUNTIME_CAPABILITY_BINDING_SCOPE_ATTESTATION_V1
            ),
            activation_authority=object(),
            activation_interlock=object(),
        )


def test_main_exposes_entrypoint_but_never_calls_it_at_startup() -> None:
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_activate_c3_closed_repair_writer_coordination_v1"
    )
    top_level_calls = [
        node
        for node in tree.body
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
    ]
    assert "activate_production_writer_coordination_v1" in ast.unparse(function)
    assert all(
        "_activate_c3_closed_repair_writer_coordination_v1"
        not in ast.unparse(node)
        for node in top_level_calls
    )
    assert source.count("_activate_c3_closed_repair_writer_coordination_v1(") == 1
    assert source.index(
        "def _activate_c3_closed_repair_writer_coordination_v1"
    ) < source.index("if CENTRAL_AUTO_START_RUNTIME:")
    assert "C3_CLOSED_REPAIR_INSTALLATION_V1 = _install_c3_closed_repair_writer_coordination_v1" in source
