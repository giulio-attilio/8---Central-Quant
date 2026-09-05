from __future__ import annotations

import threading

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_seam_v1 as seam
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module


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
