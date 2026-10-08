"""Deterministic local thread race; all evidence is the existing synthetic fake."""
import threading
import time

import pytest
import trade_registry_closed_identity_conflict_repair_runtime_startup_admission_gate_contract_v1 as gate_v1
import trade_registry_closed_identity_conflict_repair_runtime_startup_admission_gate_harness_v1 as harness


class RendezvousLock:
    """Test-only barrier: both callers reach lock entry before either acquires."""
    def __init__(self, underlying, count):
        self.underlying = underlying
        self.barrier = threading.Barrier(count, timeout=4)

    def __enter__(self):
        self.barrier.wait()
        self.underlying.acquire()
        return self

    def __exit__(self, *args):
        self.underlying.release()


@pytest.mark.parametrize("count", [2, 4])
@pytest.mark.parametrize("callback_fails", [False, True])
def test_same_request_cannot_be_consumed_twice_by_concurrent_callers(count, callback_fails):
    gate, environment, request = harness.build_synthetic_runtime_startup_admission_gate_v1()
    gate._lock = RendezvousLock(environment.atomic_lock, count)
    outcomes = []
    outcome_lock = threading.Lock()

    def run():
        try:
            with gate.startup_admission(request) as permit:
                assert permit.live_allowed is False
                assert permit.order_submission_authorized is False
                if callback_fails:
                    raise ValueError("synthetic callback failure")
            result = "ADMITTED"
        except gate_v1.RuntimeStartupAdmissionBlocked as exc:
            result = exc.reason
        except ValueError as exc:
            result = str(exc)
        except Exception as exc:
            result = type(exc).__name__
        with outcome_lock:
            outcomes.append(result)

    threads = [threading.Thread(target=run) for _ in range(count)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 6
    for thread in threads:
        thread.join(max(0, deadline - time.monotonic()))
    assert all(not thread.is_alive() for thread in threads)
    winner = "synthetic callback failure" if callback_fails else "ADMITTED"
    assert outcomes.count(winner) == 1, outcomes
    assert outcomes.count("C3_RUNTIME_STARTUP_ADMISSION_REQUEST_REPLAY_BLOCKED") == count - 1, outcomes
    assert environment.verifier_calls == 1
    assert environment.state_reads == 2
    assert environment.runtime_started is False
    assert gate.snapshot()["consumed_request_count"] == 1
    assert gate.snapshot()["active_admission"] is False


def test_replacement_verifier_instance_cannot_reuse_previous_binding():
    gate, original, request = harness.build_synthetic_runtime_startup_admission_gate_v1()
    replacement = harness.SyntheticProductionStartupEvidenceV1()
    gate._verifier = replacement.verify
    with pytest.raises(gate_v1.RuntimeStartupAdmissionBlocked, match="C3_RUNTIME_STARTUP_ADMISSION_VERIFIER_IDENTITY_MISMATCH"):
        with gate.startup_admission(request):
            pytest.fail("different verifier instance must not inherit the binding")
    assert original.state_reads == 0
    assert replacement.verifier_calls == 0


def test_refreshed_bound_method_of_same_verifier_retains_binding():
    gate, original, request = harness.build_synthetic_runtime_startup_admission_gate_v1()
    refreshed = original.verify
    assert gate_v1.production_evidence_verifier_identity_sha256_v1(refreshed) == gate._config.expected_verifier_identity_sha256
    gate._verifier = refreshed
    with gate.startup_admission(request) as permit:
        assert permit.live_allowed is False
    assert original.verifier_calls == 1
