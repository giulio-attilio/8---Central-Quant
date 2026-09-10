from __future__ import annotations

import copy
import inspect
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_seam_v1 as runtime_seam
import trade_registry_closed_identity_conflict_repair_runtime_startup_admission_composition_harness_v1 as harness


def test_final_offline_composition_reaches_only_simulated_runtime_start():
    result = harness.run_final_offline_runtime_startup_admission_composition_v1()
    assert result["ok"] is True
    assert result["status"].endswith("FINAL_OFFLINE_COMPOSITION_VERIFIED")
    assert result["bridge_result"]["ok"] is True
    assert result["restored_state"]["mode"] == "DORMANT"
    assert result["restored_state"]["generation"] == 2
    assert result["restored_state"]["writer_invocations_seen"] == 0
    assert result["binding_snapshot"]["writer_guard_bound"] is True
    assert result["simulated_runtime_started"] is True
    assert result["seam_restored_before_simulated_start"] is True


def test_final_permit_never_authorizes_live_or_orders():
    result = harness.run_final_offline_runtime_startup_admission_composition_v1()
    permit = result["permit"]
    assert permit.startup_allowed is True
    assert permit.runtime_activation_allowed is False
    assert permit.live_allowed is False
    assert permit.order_submission_authorized is False
    assert result["live_allowed"] is False
    assert result["order_submission_authorized"] is False
    assert result["no_order_sent"] is True


def test_production_shaped_projection_is_explicitly_only_a_simulation():
    result = harness.run_final_offline_runtime_startup_admission_composition_v1()
    assert result["production_evidence_simulated"] is True
    assert result["runtime_integrated"] is False
    assert result["production_ready"] is False
    assert result["real_registry_accessed"] is False
    assert result["write_executed"] is False
    assert result["registry_write"] is False


def test_harness_restores_original_real_seam_process_state():
    with runtime_seam._prebootstrap_seam_atomic_lock:
        coordinator_before = runtime_seam._coordinator
        guard_before = runtime_seam._prebootstrap_writer_guard
        activation_before = copy.deepcopy(runtime_seam._controlled_activation_state)
    result = harness.run_final_offline_runtime_startup_admission_composition_v1()
    assert result["ok"] is True
    with runtime_seam._prebootstrap_seam_atomic_lock:
        assert runtime_seam._coordinator is coordinator_before
        assert runtime_seam._prebootstrap_writer_guard is guard_before
        assert runtime_seam._controlled_activation_state == activation_before


@pytest.mark.parametrize(
    ("phase", "stage"),
    [
        ("writer_before_maintenance", "MAINTENANCE_COMPOSITION"),
        ("bridge_failed", "MAINTENANCE_COMPOSITION"),
        ("writer_before_gate", "STARTUP_ADMISSION"),
        ("maintenance_attestation_corrupt", "STARTUP_ADMISSION"),
        ("runtime_started", "STARTUP_ADMISSION"),
        ("state_drift", "STARTUP_ADMISSION"),
        ("authority_rejected", "STARTUP_ADMISSION"),
        ("signature_invalid", "STARTUP_ADMISSION"),
        ("authority_revoked", "STARTUP_ADMISSION"),
        ("authority_stale", "STARTUP_ADMISSION"),
        ("authority_receipt_corrupt", "STARTUP_ADMISSION"),
        ("verifier_failed", "STARTUP_ADMISSION"),
    ],
)
def test_every_failure_phase_stays_closed_and_does_not_start_runtime(phase, stage):
    result = harness.run_final_offline_runtime_startup_admission_composition_v1(
        fail_phase=phase
    )
    assert result["ok"] is False
    assert result["status"] == "C3_RUNTIME_STARTUP_ADMISSION_COMPOSITION_BLOCKED"
    assert result["failed_stage"] == stage
    assert result.get("simulated_runtime_started", False) is False
    assert result["live_allowed"] is False
    assert result["order_submission_authorized"] is False
    assert result["no_order_sent"] is True


def test_failed_run_also_restores_original_seam_state():
    with runtime_seam._prebootstrap_seam_atomic_lock:
        coordinator_before = runtime_seam._coordinator
        guard_before = runtime_seam._prebootstrap_writer_guard
    result = harness.run_final_offline_runtime_startup_admission_composition_v1(
        fail_phase="state_drift"
    )
    assert result["ok"] is False
    with runtime_seam._prebootstrap_seam_atomic_lock:
        assert runtime_seam._coordinator is coordinator_before
        assert runtime_seam._prebootstrap_writer_guard is guard_before


def test_harness_imports_real_seam_but_not_main_registry_or_external_clients():
    source = inspect.getsource(harness).lower()
    assert "import trade_registry_closed_identity_conflict_repair_runtime_seam_v1" in source
    forbidden = (
        "import main",
        "\nimport trade_registry\n",
        "from trade_registry import",
        "import requests",
        "import urllib",
        "import socket",
        "import os",
        "open(",
    )
    assert not any(value in source for value in forbidden)


def test_harness_file_has_no_real_storage_or_service_reference():
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "trade_registry_closed_identity_conflict_repair_runtime_startup_admission_composition_harness_v1.py"
    ).read_text(encoding="utf-8").lower()
    assert ".env" not in source
    assert "/data/trade_registry" not in source
    assert "central_data_dir" not in source
    assert "bingx" not in source
    assert "render.com" not in source


def test_runtime_main_remains_unintegrated_with_final_harness():
    root = Path(__file__).resolve().parents[1]
    source = (root / "main.py").read_text(encoding="utf-8")
    assert "runtime_startup_admission_composition_harness_v1" not in source
    assert "RuntimeStartupAdmissionGateContractV1" not in source
