"""Only synthetic temporary stores; missing lock ownership must fail closed."""
import tempfile
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_harness_v2 as harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2 as adapters
import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as storage


@pytest.fixture
def values():
    with tempfile.TemporaryDirectory(prefix="c3_multistore_locks_") as root:
        result = harness.build_authenticated_persistent_authority_production_adapters_context_v2(Path(root))
        with result["maintenance_coordinator"].maintenance_lease() as issued:
            result["permit"] = asdict(issued)
            yield result


def permit(values):
    return dict(values["permit"])


def recover(values):
    return values["multistore"].recover_multistore_v2(
        maintenance_permit=permit(values), root_authority_attestation=values["attestation"],
        now_epoch=1500)


def test_missing_lock_backend_refuses_before_either_store(values):
    values["multistore"]._lock_backend = None
    with pytest.raises(RuntimeError, match="MULTISTORE_LOCK_DEPENDENCIES_INVALID"):
        recover(values)
    assert values["transaction_port"].call_count == 0
    assert values["resolved_port"].call_count == 0


def assert_no_stores(values):
    assert values["transaction_port"].call_count == 0
    assert values["resolved_port"].call_count == 0
    assert values["prepared"].call_count == 0


def assert_available(values):
    competitor = storage.CrossPlatformInterprocessFileLockBackendV1(
        values["lock_backend"].storage_root, enabled=True)
    for namespace in values["lock_namespaces"]:
        handle = competitor.acquire(namespace, 0.02)
        assert handle is not None
        handle.release()


@pytest.mark.parametrize("field,value", [
    ("expected_lock_backend_object_identity_sha256", "f" * 64),
    ("expected_lock_storage_root_binding_sha256", "f" * 64),
    ("transaction_lock_namespace_sha256", None),
    ("resolved_lock_namespace_sha256", "UPPERCASE"),
    ("transaction_lock_namespace_sha256", "OUTER_MAINTENANCE_NAMESPACE"),
    ("lock_timeout_seconds", 0), ("lock_timeout_seconds", -1),
    ("lock_timeout_seconds", True), ("lock_timeout_seconds", float("nan")),
    ("lock_timeout_seconds", float("inf")),
])
def test_invalid_lock_configuration_fails_before_acquisition(values, monkeypatch, field, value):
    if value == "OUTER_MAINTENANCE_NAMESPACE":
        value = values["permit"]["lock_namespace_sha256"]
    values["multistore"]._config = replace(values["multistore"]._config, **{field: value})
    def forbidden(*args):
        pytest.fail("invalid dependencies must not acquire a lock")
    monkeypatch.setattr(values["lock_backend"], "acquire", forbidden)
    with pytest.raises(RuntimeError, match="MULTISTORE_LOCK_DEPENDENCIES_INVALID"):
        recover(values)
    assert_no_stores(values)


def test_duplicate_store_namespaces_fail_closed(values):
    namespace = values["lock_namespaces"][0]
    values["multistore"]._config = replace(values["multistore"]._config,
                                          resolved_lock_namespace_sha256=namespace)
    values["resolved_port"].recovery_lock_namespace_sha256 = namespace
    with pytest.raises(RuntimeError, match="MULTISTORE_LOCK_DEPENDENCIES_INVALID"):
        recover(values)
    assert_no_stores(values)


@pytest.mark.parametrize("role", ["transaction_port", "resolved_port"])
@pytest.mark.parametrize("slot", ["recovery_lock_backend", "recovery_lock_namespace_sha256"])
def test_store_must_bind_same_lock_instance_and_namespace(values, role, slot):
    setattr(values[role], slot, None)
    with pytest.raises(RuntimeError, match="MULTISTORE_LOCK_DEPENDENCIES_INVALID"):
        recover(values)
    assert_no_stores(values)


def test_recreated_backend_cannot_reuse_old_instance_pin(values):
    values["multistore"]._lock_backend = storage.CrossPlatformInterprocessFileLockBackendV1(
        values["lock_backend"].storage_root, enabled=True)
    with pytest.raises(RuntimeError, match="MULTISTORE_LOCK_DEPENDENCIES_INVALID"):
        recover(values)
    assert_no_stores(values)


def test_disabled_physical_backend_fails_closed(values):
    values["lock_backend"]._enabled = False
    with pytest.raises(RuntimeError, match="MULTISTORE_LOCK_DEPENDENCIES_INVALID"):
        recover(values)
    assert_no_stores(values)


def test_both_os_locks_held_at_both_calls_and_released_in_reverse(values, monkeypatch):
    backend = values["lock_backend"]
    competitor = storage.CrossPlatformInterprocessFileLockBackendV1(backend.storage_root, enabled=True)
    original_acquire = backend.acquire
    events = []
    def acquire(namespace, timeout):
        handle = original_acquire(namespace, timeout)
        assert handle is not None
        events.append(("acquire", namespace))
        original_release = handle.release
        def release():
            original_release()
            events.append(("release", namespace))
        monkeypatch.setattr(handle, "release", release)
        return handle
    monkeypatch.setattr(backend, "acquire", acquire)
    for role in ("transaction_port", "resolved_port"):
        original_call = values[role].recover_store_v2
        def call(*, _call=original_call, _role=role, **kwargs):
            for namespace in values["lock_namespaces"]:
                unexpected = competitor.acquire(namespace, 0.01)
                if unexpected is not None:
                    unexpected.release()
                    pytest.fail("store ran without both physical locks")
            events.append(("call", _role))
            return _call(**kwargs)
        monkeypatch.setattr(values[role], "recover_store_v2", call)
    result = recover(values)
    first, second = values["lock_namespaces"]
    assert events == [("acquire", first), ("acquire", second),
                      ("call", "transaction_port"), ("call", "resolved_port"),
                      ("release", second), ("release", first)]
    assert all(result[key] is True for key in (
        "lock_order_verified", "reverse_release_verified", "all_locks_released"))
    assert result["lock_proof_scope"] == "INJECTED_STORE_LOCKS_ONLY_V2"
    assert result["receipt_sha256"] == adapters.boundary_v2.multistore_recovery_receipt_sha256_v2(result)
    assert_available(values)


@pytest.mark.parametrize("index", [0, 1])
def test_real_lock_contention_prevents_all_store_calls_and_cleans_partial_acquisition(values, index):
    values["multistore"]._config = replace(values["multistore"]._config, lock_timeout_seconds=0.025)
    competitor = storage.CrossPlatformInterprocessFileLockBackendV1(
        values["lock_backend"].storage_root, enabled=True)
    held = competitor.acquire(values["lock_namespaces"][index], 0.02)
    assert held is not None
    try:
        with pytest.raises(RuntimeError, match="MULTISTORE_LOCK_ACQUISITION_FAILED"):
            recover(values)
        assert_no_stores(values)
        if index == 1:
            first = competitor.acquire(values["lock_namespaces"][0], 0.02)
            assert first is not None
            first.release()
    finally:
        held.release()
    assert_available(values)


@pytest.mark.parametrize("role", ["transaction_port", "resolved_port"])
def test_store_exception_releases_both_and_never_advances_bridge(values, monkeypatch, role):
    def broken(**kwargs):
        raise ValueError("synthetic store failure")
    monkeypatch.setattr(values[role], "recover_store_v2", broken)
    result = values["boundary"](permit(values))
    assert result["ok"] is False
    assert result["reason"] == "PERSISTENT_MULTISTORE_RECOVERY_FAILED_CLOSED"
    assert values["prepared"].call_count == 0
    if role == "transaction_port":
        assert values["resolved_port"].call_count == 0
    assert_available(values)


@pytest.mark.parametrize("index", [0, 1])
def test_release_failure_attempts_other_release_and_blocks_bridge(values, monkeypatch, index):
    backend = values["lock_backend"]
    original = backend.acquire
    releases = []
    def acquire(namespace, timeout):
        handle = original(namespace, timeout)
        original_release = handle.release
        def release():
            original_release()
            releases.append(namespace)
            if namespace == values["lock_namespaces"][index]:
                # Even a handle reporting released=True cannot hide an exception.
                raise OSError("synthetic release confirmation failure")
        monkeypatch.setattr(handle, "release", release)
        return handle
    monkeypatch.setattr(backend, "acquire", acquire)
    result = values["boundary"](permit(values))
    assert result["ok"] is False
    assert result["reason"] == "PERSISTENT_MULTISTORE_RECOVERY_FAILED_CLOSED"
    assert releases == list(reversed(values["lock_namespaces"]))
    assert values["prepared"].call_count == 0
    assert_available(values)


def test_second_acquisition_exception_releases_first(values, monkeypatch):
    backend = values["lock_backend"]
    original = backend.acquire
    def acquire(namespace, timeout):
        if namespace == values["lock_namespaces"][1]:
            raise OSError("synthetic acquisition error")
        return original(namespace, timeout)
    monkeypatch.setattr(backend, "acquire", acquire)
    with pytest.raises(OSError, match="synthetic acquisition error"):
        recover(values)
    assert_no_stores(values)
    assert_available(values)


def test_store_cannot_change_binding_of_next_call_via_shared_arguments(values, monkeypatch):
    original = values["transaction_port"].recover_store_v2
    def mutate_after_receipt(**kwargs):
        receipt = original(**kwargs)
        kwargs["maintenance_permit"]["maintenance_epoch"] = "e" * 64
        kwargs["root_authority_attestation"]["attestation_sha256"] = "e" * 64
        return receipt
    monkeypatch.setattr(values["transaction_port"], "recover_store_v2", mutate_after_receipt)
    result = recover(values)
    assert result["maintenance_epoch"] == permit(values)["maintenance_epoch"]
    assert result["root_authority_attestation_sha256"] == values["attestation"]["attestation_sha256"]
    assert result["ok"] is True
    assert_available(values)


@pytest.mark.parametrize("index", [0, 1])
def test_lock_returned_after_total_deadline_is_released_without_store_calls(values, monkeypatch, index):
    clock = [100.0]
    # Replace only this module's clock reference; the OS backend keeps its clock.
    monkeypatch.setattr(adapters, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    backend = values["lock_backend"]
    original = backend.acquire
    def acquire(namespace, timeout):
        handle = original(namespace, timeout)
        if namespace == values["lock_namespaces"][index]:
            clock[0] += 2.0
        return handle
    monkeypatch.setattr(backend, "acquire", acquire)
    with pytest.raises(RuntimeError, match="MULTISTORE_LOCK_DEADLINE_EXCEEDED"):
        recover(values)
    assert_no_stores(values)
    assert_available(values)


def test_early_release_by_store_prevents_next_store_and_success_receipt(values, monkeypatch):
    backend = values["lock_backend"]
    original_acquire = backend.acquire
    handles = []
    def acquire(namespace, timeout):
        handle = original_acquire(namespace, timeout)
        handles.append(handle)
        return handle
    monkeypatch.setattr(backend, "acquire", acquire)
    original_call = values["transaction_port"].recover_store_v2
    def early_release(**kwargs):
        receipt = original_call(**kwargs)
        handles[1].release()
        return receipt
    monkeypatch.setattr(values["transaction_port"], "recover_store_v2", early_release)
    result = values["boundary"](permit(values))
    assert result["ok"] is False
    assert result["reason"] == "PERSISTENT_MULTISTORE_RECOVERY_FAILED_CLOSED"
    assert values["resolved_port"].call_count == 0
    assert values["prepared"].call_count == 0
    assert_available(values)


def test_unconfirmed_release_is_not_reported_as_success(values, monkeypatch):
    backend = values["lock_backend"]
    original_acquire = backend.acquire
    unreleased = []
    def acquire(namespace, timeout):
        handle = original_acquire(namespace, timeout)
        if namespace == values["lock_namespaces"][1]:
            unreleased.append(handle.release)
            monkeypatch.setattr(handle, "release", lambda: None)
        return handle
    monkeypatch.setattr(backend, "acquire", acquire)
    try:
        with pytest.raises(RuntimeError, match="MULTISTORE_LOCK_RELEASE_FAILED"):
            recover(values)
        # Failure to release the second lock must not suppress release of first.
        first = original_acquire(values["lock_namespaces"][0], 0.02)
        assert first is not None
        first.release()
    finally:
        for release in unreleased:
            release()
    assert_available(values)
