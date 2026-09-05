from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_seam_v1 as seam
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module


ROOT = Path(__file__).resolve().parents[1]


class _SyntheticLockHandle:
    def release(self) -> None:
        return None


class _SyntheticLockBackend:
    def acquire(self, namespace: str, timeout_seconds: float):
        return _SyntheticLockHandle()


class _SyntheticLeaseStore:
    def read(self, namespace: str):
        return None

    def write(self, namespace: str, lease):
        return None


def _enabled_coordinator(*, register_all: bool = True):
    coordinator = (
        coordinator_module.build_closed_repair_writer_runtime_coordinator_v1(
            config=coordinator_module.WriterRuntimeCoordinatorConfigV1(
                enabled=True
            ),
            lock_backend=_SyntheticLockBackend(),
            lease_store=_SyntheticLeaseStore(),
            clock=lambda: 1.0,
            nonce_source=lambda: "synthetic-nonce",
        )
    )
    if register_all:
        coordinator.register_all_declared_writers()
    return coordinator


def _activation_evidence(**changes):
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
    }
    evidence.update(changes)
    evidence["activation_evidence_sha256"] = (
        seam.controlled_activation_evidence_sha256_v1(evidence)
    )
    return evidence


def test_dormant_seam_is_default_off_and_has_no_external_authority() -> None:
    status = seam.c3_closed_repair_writer_coordination_status_v1()

    assert status == {
        "ok": True,
        "status": "C3_WRITER_COORDINATION_DORMANT_DEFAULT_OFF",
        "installed": True,
        "enabled": False,
        "coordination_ready": False,
        "runtime_activation_allowed": False,
        "registered_writer_count": 0,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
    }


def test_default_off_mutation_context_preserves_result() -> None:
    with seam._c3_closed_repair_writer_mutation_v1(
        "TRADE_REGISTRY_UPDATE_OPEN_TRADE"
    ) as permit:
        assert permit.admitted is True
        assert permit.coordinated is False
        assert permit.status == "COORDINATOR_DEFAULT_OFF_PASSTHROUGH"


def test_default_off_mutation_decorator_preserves_result() -> None:
    @seam._c3_closed_repair_writer_mutation_v1(
        "MAIN_SYNC_MANUAL_REGISTER_OPEN"
    )
    def callback(value: int) -> int:
        return value + 1

    assert callback(2) == 3


def test_decorator_recreates_context_for_concurrent_calls() -> None:
    decorator = seam._c3_closed_repair_writer_mutation_v1(
        "MAIN_SYNC_MANUAL_REGISTER_OPEN"
    )
    assert decorator._recreate_cm() is not decorator

    barrier = threading.Barrier(2)
    results: list[int] = []
    errors: list[BaseException] = []

    @decorator
    def callback(value: int) -> int:
        barrier.wait(timeout=2.0)
        return value + 1

    def invoke(value: int) -> None:
        try:
            results.append(callback(value))
        except BaseException as exc:  # pragma: no cover - diagnostic capture
            errors.append(exc)

    threads = [threading.Thread(target=invoke, args=(value,)) for value in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3.0)

    assert errors == []
    assert sorted(results) == [2, 3]
    assert all(not thread.is_alive() for thread in threads)


def test_seam_rejects_an_enabled_coordinator() -> None:
    class LockHandle:
        def release(self) -> None:
            return None

    class LockBackend:
        def acquire(self, namespace: str, timeout_seconds: float):
            return LockHandle()

    class LeaseStore:
        def read(self, namespace: str):
            return None

        def write(self, namespace: str, lease):
            return None

    enabled = coordinator_module.build_closed_repair_writer_runtime_coordinator_v1(
        config=coordinator_module.WriterRuntimeCoordinatorConfigV1(enabled=True),
        lock_backend=LockBackend(),
        lease_store=LeaseStore(),
        clock=lambda: 1.0,
        nonce_source=lambda: "nonce",
    )

    with pytest.raises(
        coordinator_module.WriterRuntimeCoordinationBlocked,
        match="C3_RUNTIME_ACTIVATION_FORBIDDEN_BY_DORMANT_SEAM",
    ):
        seam.install_dormant_c3_closed_repair_writer_coordinator_v1(enabled)


def test_controlled_installer_is_default_off_and_requires_scope() -> None:
    coordinator = _enabled_coordinator()
    evidence = _activation_evidence()

    with pytest.raises(
        coordinator_module.WriterRuntimeCoordinationBlocked,
        match="C3_CONTROLLED_ACTIVATION_DEFAULT_OFF",
    ):
        seam.install_controlled_c3_closed_repair_writer_coordinator_v1(
            coordinator,
            activation_evidence=evidence,
            kill_switch=lambda: False,
        )

    with pytest.raises(
        coordinator_module.WriterRuntimeCoordinationBlocked,
        match="C3_CONTROLLED_ACTIVATION_SCOPE_ATTESTATION_REQUIRED",
    ):
        seam.install_controlled_c3_closed_repair_writer_coordinator_v1(
            coordinator,
            enabled=True,
            activation_evidence=evidence,
            kill_switch=lambda: False,
        )


def test_controlled_installer_rejects_tampered_or_unsafe_evidence() -> None:
    coordinator = _enabled_coordinator()
    tampered = _activation_evidence()
    tampered["source_hashes_verified"] = False

    with pytest.raises(
        coordinator_module.WriterRuntimeCoordinationBlocked,
        match="C3_CONTROLLED_ACTIVATION_EVIDENCE_HASH_MISMATCH",
    ):
        seam.install_controlled_c3_closed_repair_writer_coordinator_v1(
            coordinator,
            enabled=True,
            scope_attestation=(
                seam.C3_CONTROLLED_RUNTIME_ACTIVATION_SCOPE_ATTESTATION_V1
            ),
            activation_evidence=tampered,
            kill_switch=lambda: False,
        )

    unsafe = _activation_evidence(
        trading_controls={
            **_activation_evidence()["trading_controls"],
            "enable_real_trading": True,
        }
    )
    with pytest.raises(
        coordinator_module.WriterRuntimeCoordinationBlocked,
        match="C3_CONTROLLED_ACTIVATION_EVIDENCE_UNSAFE",
    ):
        seam.install_controlled_c3_closed_repair_writer_coordinator_v1(
            coordinator,
            enabled=True,
            scope_attestation=(
                seam.C3_CONTROLLED_RUNTIME_ACTIVATION_SCOPE_ATTESTATION_V1
            ),
            activation_evidence=unsafe,
            kill_switch=lambda: False,
        )


def test_controlled_installer_requires_all_writers_and_clear_kill_switch() -> None:
    evidence = _activation_evidence()
    missing_writers = _enabled_coordinator(register_all=False)

    with pytest.raises(
        coordinator_module.WriterRuntimeCoordinationBlocked,
        match="C3_CONTROLLED_ACTIVATION_COORDINATOR_NOT_QUIESCENT",
    ):
        seam.install_controlled_c3_closed_repair_writer_coordinator_v1(
            missing_writers,
            enabled=True,
            scope_attestation=(
                seam.C3_CONTROLLED_RUNTIME_ACTIVATION_SCOPE_ATTESTATION_V1
            ),
            activation_evidence=evidence,
            kill_switch=lambda: False,
        )

    with pytest.raises(
        coordinator_module.WriterRuntimeCoordinationBlocked,
        match="C3_CONTROLLED_ACTIVATION_KILL_SWITCH_ENGAGED",
    ):
        seam.install_controlled_c3_closed_repair_writer_coordinator_v1(
            _enabled_coordinator(),
            enabled=True,
            scope_attestation=(
                seam.C3_CONTROLLED_RUNTIME_ACTIVATION_SCOPE_ATTESTATION_V1
            ),
            activation_evidence=evidence,
            kill_switch=lambda: True,
        )


def test_controlled_installer_reports_full_vector_and_kill_switch_fails_closed() -> None:
    kill_switch = {"engaged": False}
    coordinator = _enabled_coordinator()
    try:
        status = seam.install_controlled_c3_closed_repair_writer_coordinator_v1(
            coordinator,
            enabled=True,
            scope_attestation=(
                seam.C3_CONTROLLED_RUNTIME_ACTIVATION_SCOPE_ATTESTATION_V1
            ),
            activation_evidence=_activation_evidence(),
            kill_switch=lambda: kill_switch["engaged"],
        )

        assert status["ok"] is True
        assert status["enabled"] is True
        assert status["coordination_ready"] is True
        assert status["runtime_activation_allowed"] is True
        assert status["registered_writer_count"] == 19
        assert status["all_writers_registered"] is True
        assert status["inflight_mutations"] == 0
        assert status["shared_lock_backend_ready"] is True
        assert status["maintenance_lease_store_ready"] is True
        assert status["registry_interlock_ready"] is True
        assert status["activation_receipt_verified"] is True
        assert status["source_hashes_verified"] is True
        assert status["rollback_ready"] is True
        assert status["kill_switch_ready"] is True
        assert status["real_registry_accessed"] is False
        assert status["network_accessed"] is False
        assert status["no_order_sent"] is True

        with seam._c3_closed_repair_writer_mutation_v1(
            "TRADE_REGISTRY_UPDATE_OPEN_TRADE"
        ) as permit:
            assert permit.coordinated is True
            assert permit.shared_lock_acquired is True

        kill_switch["engaged"] = True
        blocked_status = seam.c3_closed_repair_writer_coordination_status_v1()
        assert blocked_status["coordination_ready"] is False
        assert blocked_status["runtime_activation_allowed"] is False
        assert blocked_status["kill_switch_engaged"] is True
        with pytest.raises(
            coordinator_module.WriterRuntimeCoordinationBlocked,
            match="C3_RUNTIME_KILL_SWITCH_ENGAGED",
        ):
            with seam._c3_closed_repair_writer_mutation_v1(
                "TRADE_REGISTRY_UPDATE_OPEN_TRADE"
            ):
                pass
    finally:
        seam.install_dormant_c3_closed_repair_writer_coordinator_v1(
            coordinator_module.build_closed_repair_writer_runtime_coordinator_v1()
        )


def test_controlled_installer_remains_unreferenced_by_runtime_main() -> None:
    source = (ROOT / "main.py").read_text(encoding="utf-8")

    assert "install_controlled_c3_closed_repair_writer_coordinator_v1" not in source
