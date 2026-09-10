from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_startup_admission_gate_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_startup_admission_gate_harness_v1 as harness


def _build(**kwargs):
    return harness.build_synthetic_runtime_startup_admission_gate_v1(**kwargs)


def test_gate_is_default_off_without_reading_state_or_calling_authority():
    gate, environment, request = _build(gate_enabled=False)
    assert gate.snapshot()["default_off"] is True
    with pytest.raises(contract.RuntimeStartupAdmissionBlocked) as raised:
        with gate.startup_admission(request):
            pass
    assert raised.value.reason == "C3_RUNTIME_STARTUP_ADMISSION_GATE_DEFAULT_OFF"
    assert environment.state_reads == 0
    assert environment.verifier_calls == 0


def test_complete_production_shaped_evidence_issues_startup_only_permit():
    result = harness.run_synthetic_runtime_startup_admission_gate_v1()
    permit = result["permit"]
    assert result["ok"] is True
    assert permit.startup_allowed is True
    assert permit.same_atomic_lock is True
    assert permit.runtime_activation_allowed is False
    assert permit.live_allowed is False
    assert permit.order_submission_authorized is False
    assert result["runtime_integrated"] is False
    assert result["no_order_sent"] is True


def test_permit_and_config_repr_protect_all_digests():
    gate, _, request = _build()
    with gate.startup_admission(request) as permit:
        rendered = repr(permit)
        assert request["evidence"]["startup_state"]["process_boot_epoch_sha256"] not in rendered
        assert request["evidence"]["seam_binding"]["binding_receipt_sha256"] not in rendered
        assert request["evidence"]["maintenance_completion"]["completion_receipt_sha256"] not in rendered
    config = contract.RuntimeStartupAdmissionGateConfigV1(
        enabled=True,
        scope_attestation="hidden-scope",
        expected_authority_root_sha256="a" * 64,
        expected_verifier_identity_sha256="b" * 64,
    )
    assert "hidden-scope" not in repr(config)
    assert "a" * 64 not in repr(config)
    assert "b" * 64 not in repr(config)


@pytest.mark.parametrize(
    "phase",
    [
        "unsafe_trading",
        "writer_seen",
        "runtime_started",
        "guard_missing",
        "synthetic_state",
        "seam_incomplete",
        "generation_mismatch",
        "maintenance_failed",
        "unresolved_transactions",
        "conflict_remaining",
        "lease_not_released",
        "network_accessed",
        "order_sent",
    ],
)
def test_any_incomplete_or_unsafe_evidence_blocks_startup(phase):
    gate, environment, request = _build(fail_phase=phase)
    with pytest.raises(contract.RuntimeStartupAdmissionBlocked) as raised:
        with gate.startup_admission(request):
            pass
    assert raised.value.reason == "C3_RUNTIME_STARTUP_ADMISSION_EVIDENCE_UNSAFE"
    assert environment.verifier_calls == 0
    assert environment.runtime_started is False


@pytest.mark.parametrize(
    "phase",
    [
        "authority_rejected",
        "signature_invalid",
        "authority_revoked",
        "authority_stale",
        "authority_receipt_corrupt",
    ],
)
def test_invalid_authenticated_authority_receipt_blocks_startup(phase):
    gate, environment, request = _build(fail_phase=phase)
    with pytest.raises(contract.RuntimeStartupAdmissionBlocked) as raised:
        with gate.startup_admission(request):
            pass
    assert raised.value.reason == "C3_RUNTIME_STARTUP_ADMISSION_AUTHORITY_INVALID"
    assert environment.verifier_calls == 1
    assert environment.runtime_started is False


def test_authority_exception_blocks_startup():
    gate, environment, request = _build(fail_phase="verifier_failed")
    with pytest.raises(contract.RuntimeStartupAdmissionBlocked) as raised:
        with gate.startup_admission(request):
            pass
    assert raised.value.reason == "C3_RUNTIME_STARTUP_ADMISSION_AUTHORITY_FAILED"
    assert environment.runtime_started is False


def test_state_drift_between_authority_checks_blocks_startup():
    gate, environment, request = _build(fail_phase="state_drift")
    with pytest.raises(contract.RuntimeStartupAdmissionBlocked) as raised:
        with gate.startup_admission(request):
            pass
    assert raised.value.reason == "C3_RUNTIME_STARTUP_ADMISSION_STATE_DRIFT"
    assert environment.verifier_calls == 1
    assert environment.runtime_started is False


def test_state_provider_exception_blocks_before_authority():
    gate, environment, request = _build(fail_phase="state_read_failed")
    with pytest.raises(contract.RuntimeStartupAdmissionBlocked) as raised:
        with gate.startup_admission(request):
            pass
    assert raised.value.reason == "C3_RUNTIME_STARTUP_ADMISSION_STATE_READ_FAILED"
    assert environment.verifier_calls == 0


def test_request_hash_tamper_blocks_before_state_read():
    gate, environment, request = _build(fail_phase="request_hash_corrupt")
    with pytest.raises(contract.RuntimeStartupAdmissionBlocked) as raised:
        with gate.startup_admission(request):
            pass
    assert raised.value.reason == "C3_RUNTIME_STARTUP_ADMISSION_REQUEST_HASH_MISMATCH"
    assert environment.state_reads == 0
    assert environment.verifier_calls == 0


def test_request_is_one_shot_even_when_runtime_is_not_committed():
    gate, _, request = _build()
    with gate.startup_admission(request):
        pass
    with pytest.raises(contract.RuntimeStartupAdmissionBlocked) as raised:
        with gate.startup_admission(request):
            pass
    assert raised.value.reason == "C3_RUNTIME_STARTUP_ADMISSION_REQUEST_REPLAY_BLOCKED"


def test_nested_admission_is_forbidden():
    gate, _, request = _build()
    with gate.startup_admission(request):
        with pytest.raises(contract.RuntimeStartupAdmissionBlocked) as raised:
            with gate.startup_admission(request):
                pass
        assert raised.value.reason == "C3_RUNTIME_STARTUP_ADMISSION_NESTED_FORBIDDEN"


def test_wrong_verifier_identity_blocks_without_calling_it():
    _, environment, request = _build()
    gate = contract.RuntimeStartupAdmissionGateContractV1(
        startup_state=environment.startup_state,
        production_evidence_verifier=environment.verify,
        atomic_lock=environment.atomic_lock,
        config=contract.RuntimeStartupAdmissionGateConfigV1(
            enabled=True,
            scope_attestation=contract.RUNTIME_STARTUP_ADMISSION_GATE_SCOPE_ATTESTATION_V1,
            expected_authority_root_sha256=environment.authority_root_sha256,
            expected_verifier_identity_sha256="0" * 64,
        ),
    )
    with pytest.raises(contract.RuntimeStartupAdmissionBlocked) as raised:
        with gate.startup_admission(request):
            pass
    assert raised.value.reason == "C3_RUNTIME_STARTUP_ADMISSION_VERIFIER_IDENTITY_MISMATCH"
    assert environment.verifier_calls == 0


def test_wrong_authority_root_blocks_authenticated_receipt():
    _, environment, request = _build()
    verifier_sha = contract.production_evidence_verifier_identity_sha256_v1(
        environment.verify
    )
    gate = contract.RuntimeStartupAdmissionGateContractV1(
        startup_state=environment.startup_state,
        production_evidence_verifier=environment.verify,
        atomic_lock=environment.atomic_lock,
        config=contract.RuntimeStartupAdmissionGateConfigV1(
            enabled=True,
            scope_attestation=contract.RUNTIME_STARTUP_ADMISSION_GATE_SCOPE_ATTESTATION_V1,
            expected_authority_root_sha256="9" * 64,
            expected_verifier_identity_sha256=verifier_sha,
        ),
    )
    with pytest.raises(contract.RuntimeStartupAdmissionBlocked) as raised:
        with gate.startup_admission(request):
            pass
    assert raised.value.reason == "C3_RUNTIME_STARTUP_ADMISSION_AUTHORITY_INVALID"


def test_extra_request_or_evidence_fields_are_rejected():
    gate, environment, request = _build()
    request["unexpected"] = True
    request["request_sha256"] = contract.runtime_startup_admission_request_sha256_v1(
        request
    )
    with pytest.raises(contract.RuntimeStartupAdmissionBlocked) as raised:
        with gate.startup_admission(request):
            pass
    assert raised.value.reason == "C3_RUNTIME_STARTUP_ADMISSION_REQUEST_INVALID"
    assert environment.verifier_calls == 0


def test_gate_does_not_integrate_or_authorize_live():
    gate, _, request = _build()
    status = gate.snapshot()
    assert status["runtime_integrated"] is False
    assert status["production_ready"] is False
    assert status["live_allowed"] is False
    assert status["order_submission_authorized"] is False
    with gate.startup_admission(request) as permit:
        assert permit.runtime_activation_allowed is False
        assert permit.live_allowed is False
        assert permit.order_submission_authorized is False


def test_contract_and_harness_have_no_runtime_or_external_imports():
    source = "\n".join(
        inspect.getsource(module).lower() for module in (contract, harness)
    )
    forbidden = (
        "import main",
        "\nimport trade_registry\n",
        "from trade_registry import",
        "import requests",
        "import urllib",
        "import socket",
        "import os",
        "from pathlib",
        "open(",
    )
    assert not any(value in source for value in forbidden)


def test_files_do_not_reference_real_storage_or_services():
    root = Path(__file__).resolve().parents[1]
    paths = (
        root / "trade_registry_closed_identity_conflict_repair_runtime_startup_admission_gate_contract_v1.py",
        root / "trade_registry_closed_identity_conflict_repair_runtime_startup_admission_gate_harness_v1.py",
    )
    source = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)
    assert ".env" not in source
    assert "/data/trade_registry" not in source
    assert "central_data_dir" not in source
    assert "bingx" not in source
    assert "render.com" not in source
