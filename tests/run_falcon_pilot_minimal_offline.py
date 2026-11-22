"""Run the existing Falcon safety regressions without external access.

Usage: python3 -I tests/run_falcon_pilot_minimal_offline.py
       [--upstash-sdk-contract|--account-client-order-authority|--live-position-risk-gate|--position-snapshot-reuse|--paper-registry-source-preview|--paper-registry-source-capture|--falcon-telegram-command-auth|--telegram-command-auth|--central-telegram-command-auth|--history-memory-state-io|--history-render-rewrite-guard|--lifecycle-shadow-bridge-storage-guard|--central-runtime-lock-guard|--paper-main-storage-guard|--data-status-lock-guard|--arb-tail-storage-guard|--policy-storage-guard|--journal-learning-storage-guard|--memory-profiler-storage-guard|--paper-integrated-disk-guard-no-flask|--predator-daily-summary-storage-guard|--personal-lifecycle-no-ccxt]
Some tests import main.py, so runtime auto-start is disabled before collection.
Pytest is loaded only after network, subprocess and .env-file access are denied.
"""

import builtins
import http.client
import inspect
import io
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import urllib.request


class OfflineBoundaryViolation(BaseException):
    pass


def forbidden(*args, **kwargs):
    raise OfflineBoundaryViolation("offline boundary violated")


_ORIGINAL_SOCKET = socket.socket
_LOOPBACK_SERVER_ONLY = sys.argv[1:] in (
    [],
    ["--drain-only"],
    ["--drain-regression"],
    ["--extra"],
    ["--telegram-notification-policy"],
)


class GuardedSocket(_ORIGINAL_SOCKET):
    def __init__(self, *args, **kwargs):
        # urllib3 probes IPv6 support while importing ccxt. Report unavailable
        # without creating a socket in either offline mode.
        caller = inspect.currentframe().f_back
        if (
            caller.f_code.co_name == "_has_ipv6"
            and Path(caller.f_code.co_filename).as_posix().endswith("urllib3/util/connection.py")
            and args == (socket.AF_INET6,)
            and not kwargs
        ):
            raise OSError("IPv6 capability probe disabled in offline tests")
        if _LOOPBACK_SERVER_ONLY:
            family = args[0] if args else kwargs.get("family", socket.AF_INET)
            socktype = args[1] if len(args) > 1 else kwargs.get("type", socket.SOCK_STREAM)
            if family == socket.AF_INET and socktype == socket.SOCK_STREAM:
                super().__init__(*args, **kwargs)
                return
            forbidden()
        forbidden()

    def bind(self, address):
        if (
            _LOOPBACK_SERVER_ONLY
            and isinstance(address, tuple)
            and address
            and address[0] == "127.0.0.1"
        ):
            return super().bind(address)
        forbidden()

    def listen(self, *args, **kwargs):
        if _LOOPBACK_SERVER_ONLY:
            return super().listen(*args, **kwargs)
        forbidden()

    def connect(self, *args, **kwargs):
        forbidden()

    def connect_ex(self, *args, **kwargs):
        forbidden()

    def accept(self):
        forbidden()

    def send(self, *args, **kwargs):
        forbidden()

    def sendall(self, *args, **kwargs):
        forbidden()

    def sendto(self, *args, **kwargs):
        forbidden()


def guarded_open(original):
    def opener(path, *args, **kwargs):
        if isinstance(path, (str, bytes, os.PathLike)) and Path(path).name.lower().startswith(".env"):
            raise OfflineBoundaryViolation("secret file access denied")
        return original(path, *args, **kwargs)
    return opener


socket.socket = GuardedSocket
socket.create_connection = forbidden
socket.getaddrinfo = forbidden
socket.gethostbyname = forbidden
http.client.HTTPConnection.connect = forbidden
http.client.HTTPSConnection.connect = forbidden
urllib.request.urlopen = forbidden
_ORIGINAL_POPEN = subprocess.Popen


class GuardedPopen(_ORIGINAL_POPEN):
    def __init__(self, *args, **kwargs):
        forbidden()


subprocess.Popen = GuardedPopen
subprocess.run = forbidden
os.system = forbidden
builtins.open = guarded_open(builtins.open)
io.open = guarded_open(io.open)
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
os.environ["CENTRAL_AUTO_START_RUNTIME"] = "false"
_ISOLATED_DATA_DIR = tempfile.TemporaryDirectory(prefix="central-quant-offline-data-")
os.environ["CENTRAL_DATA_DIR"] = _ISOLATED_DATA_DIR.name
os.environ["DATA_DIR"] = _ISOLATED_DATA_DIR.name
os.environ["TRADE_REGISTRY_FILE"] = str(
    Path(_ISOLATED_DATA_DIR.name) / "trade_registry.json"
)
os.environ["TRADE_LIFECYCLE_SHADOW_DATA_DIR"] = _ISOLATED_DATA_DIR.name

import pytest  # noqa: E402 - only after guards


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CASES = (
    "test_runtime_drain_v1.py",
    "test_main_runtime_drain_contract_v1.py",
    "test_falcon_single_live_execution_path_v1.py",
    "test_falcon_management_safety_v1.py",
    "test_falcon_real_position_ownership_limit_v1.py",
    "test_falcon_real_pilot_preflight_fail_closed_v1.py",
    "test_main_real_pilot_guard_fail_closed_v1.py",
    "test_account_client_order_id_v1.py",
    "test_account_client_order_writer_contract_v1.py",
    "test_runtime_file_lock_fail_closed_v1.py",
    "test_live_central_risk_gate_fail_closed_v1.py",
)
EXTRA_CASES = (
    "test_runtime_drain_v1.py",
    "test_trade_lifecycle_shadow_runtime_adapter.py",
    "test_registry_remaining_writers_atomic_rmw_v1.py",
    "test_trade_registry_atomic_durable_write_v1.py",
    "test_trade_registry_reset_serialization_v1.py",
    "test_falcon_central_only_reconciliation.py",
    "test_falcon_initial_stop_failure_containment_v1.py",
    "test_falcon_terminal_disaster_stop_emergency_recovery_v1.py",
    "test_falcon_manual_close_outcome_reconciliation_v1.py",
    "test_real_close_reconciliation_v11.py",
    "test_startup_disk_forensics.py",
    "test_broker_order_constraints_fail_closed_v1.py",
    "test_broker_account_client_order_boundary_v1.py",
    "test_broker_managed_close_timeout_semantics_v1.py",
    "test_broker_managed_entry_cancel_v1.py",
    "test_broker_entry_fill_stop_sizing_v1.py",
    "test_bingx_ccxt_stop_readback_contract_v1.py",
    "test_personal_http_auth_gate_v1.py",
    "test_auto_real_execution_bridge_route_auth_v1.py",
    "test_disaster_stop_fallback_route_auth_v1.py",
    "test_execution_engine_public_health_redaction_v1.py",
    "test_live_central_risk_gate_fail_closed_v1.py",
    "test_falcon_positions_read_fail_closed_v1.py",
    "test_live_position_reconciliation_risk_gate_v1.py",
    "test_trading_mode_defaults_fail_closed_v1.py",
)


if __name__ == "__main__":
    if sys.argv[1:] == ["--extra"]:
        cases = EXTRA_CASES
    elif sys.argv[1:] == ["--drain-only"]:
        cases = ("test_runtime_drain_v1.py", "test_main_runtime_drain_contract_v1.py")
    elif sys.argv[1:] == ["--drain-regression"]:
        cases = (
            "test_runtime_drain_v1.py",
            "test_main_runtime_drain_contract_v1.py",
            "test_falcon_initial_stop_failure_containment_v1.py",
            "test_falcon_management_safety_v1.py",
        )
    elif sys.argv[1:] in (["--registry-lock-audit"], ["--registry-writers"]):
        cases = (
            "test_registry_remaining_writers_atomic_rmw_v1.py",
            "test_trade_registry_atomic_durable_write_v1.py",
        )
    elif sys.argv[1:] == ["--registry-atomic-storage"]:
        cases = ("test_trade_registry_atomic_durable_write_v1.py",)
    elif sys.argv[1:] == ["--registry-sync"]:
        cases = ("test_main_traderegistry_sync_v2_ownership.py",)
    elif sys.argv[1:] == ["--registry-v2-migration-audit"]:
        cases = ("test_registry_v2_migration_audit.py",)
    elif sys.argv[1:] == ["--registry-stop-evidence"]:
        cases = ("test_trade_registry_closed_identity_conflict_sources_v1.py",)
        filters = ["-k", "stop_evidence"]
    elif sys.argv[1:] == ["--paper-registry-source-preview"]:
        cases = ("test_paper_registry_source_preview.py",)
    elif sys.argv[1:] == ["--paper-registry-source-capture"]:
        cases = ("test_paper_registry_source_capture.py",)
    elif sys.argv[1:] == ["--falcon-telegram-command-auth"]:
        cases = (
            "test_falcon_telegram_command_auth_v1.py",
            "test_telegram_command_auth_v1.py",
        )
    elif sys.argv[1:] == ["--telegram-command-auth"]:
        cases = (
            "test_falcon_telegram_command_auth_v1.py",
            "test_telegram_command_auth_v1.py",
            "test_central_telegram_command_auth_v1.py",
        )
    elif sys.argv[1:] == ["--central-telegram-command-auth"]:
        cases = (
            "test_central_telegram_command_auth_v1.py",
        )
    elif sys.argv[1:] == ["--history-memory-state-io"]:
        cases = (
            "test_history_events_memory_containment.py",
            "test_history_events_rotation_v1.py",
            "test_closed_trade_key_index_v1.py",
            "test_real_pnl_r_mapper_closed_identity_v1.py",
        )
    elif sys.argv[1:] == ["--history-storage-serialization"]:
        cases = ("test_history_events_memory_containment.py",)
    elif sys.argv[1:] == ["--history-render-rewrite-guard"]:
        cases = ("test_history_rewrite_render_block_v1.py",)
    elif sys.argv[1:] == ["--lifecycle-shadow-bridge-storage-guard"]:
        cases = ("test_trade_lifecycle_shadow_bridge.py",)
    elif sys.argv[1:] == ["--central-runtime-lock-guard"]:
        cases = ("test_runtime_file_lock_fail_closed_v1.py",)
    elif sys.argv[1:] == ["--paper-main-storage-guard"]:
        cases = ("test_main_paper_audit_storage_guard_v1.py",)
    elif sys.argv[1:] == ["--arb-tail-storage-guard"]:
        cases = ("test_auto_real_execution_bridge_bounded_tail_reader_v1.py",)
    elif sys.argv[1:] == ["--data-status-lock-guard"]:
        cases = ("test_main_paper_audit_storage_guard_v1.py",)
    elif sys.argv[1:] == ["--policy-storage-guard"]:
        cases = (
            "test_policy_persistent_storage_guard_v1.py",
            "test_history_eventbus_smoke.py",
        )
    elif sys.argv[1:] == ["--journal-learning-storage-guard"]:
        cases = (
            "test_policy_persistent_storage_guard_v1.py",
            "test_lifecycle_bounded_tail_reader_v2.py",
            "test_automatic_learning_refresh.py",
        )
    elif sys.argv[1:] == ["--memory-profiler-storage-guard"]:
        cases = (
            "test_memory_profiler_storage_guard_v1.py",
            "test_memory_gc_coordinator_v1.py",
        )
    elif sys.argv[1:] == ["--predator-daily-summary-storage-guard"]:
        cases = ("test_predator_daily_summary_paper_storage_v1.py",)
    elif sys.argv[1:] == ["--can-open-risk"]:
        cases = (
            "test_history_eventbus_smoke.py",
            "test_falcon_single_live_execution_path_v1.py",
        )
    elif sys.argv[1:] == ["--live-position-risk-gate"]:
        cases = (
            "test_live_position_reconciliation_risk_gate_v1.py",
            "test_live_central_risk_gate_fail_closed_v1.py",
            "test_main_position_snapshot_reuse_v1.py",
        )
    elif sys.argv[1:] == ["--position-snapshot-reuse"]:
        cases = ("test_main_position_snapshot_reuse_v1.py",)
    elif sys.argv[1:] == ["--c3-dormant-startup"]:
        cases = (
            "test_c3_dormant_startup_same_coordinator_v2.py",
            "test_c3_dormant_root_head_startup_integration_v1.py",
        )
    elif sys.argv[1:] == ["--c3-dormant-startup-verbose"]:
        cases = (
            "test_c3_dormant_startup_same_coordinator_v2.py",
            "test_c3_dormant_root_head_startup_integration_v1.py",
        )
    elif sys.argv[1:] == ["--market-data-throttle"]:
        cases = (
            "test_exchange_manager_throttle_v1.py",
            "test_exchange_ohlcv_rate_limit_v1.py",
            "test_exchange_throttle_policy_v1.py",
            "test_predator_deferred_m15_fetch_v1.py",
        )
    elif sys.argv[1:] == ["--broker-paper-disk-guard"]:
        cases = (
            "test_broker_real_pilot_disk_space_guard_v1.py",
            "test_broker_order_constraints_fail_closed_v1.py",
            "test_broker_account_client_order_boundary_v1.py",
        )
    elif sys.argv[1:] == ["--broker-log-storage-guard"]:
        cases = ("test_broker_execution_log_storage_guard_v1.py",)
    elif sys.argv[1:] == ["--registry-v2-paper-storage-guard"]:
        cases = (
            "test_registry_v2_reader.py",
            "test_registry_v2_core.py",
            "test_registry_v2_paper_runtime_adapter.py",
            "test_registry_v2_paper_runtime_integration.py",
        )
    elif sys.argv[1:] == ["--paper-integrated-disk-guard"]:
        cases = (
            "test_paper_executor_integrated_idempotency_v1.py",
            "test_paper_executor_data_dir_resolution_v1.py",
            "test_execution_pipeline_status_paper_state_v1.py",
            "test_adaptive_weights_data_dir_guard_v1.py",
            "test_paper_state_storage_render_paths_v1.py",
            "test_main_paper_audit_storage_guard_v1.py",
            "test_runtime_file_lock_fail_closed_v1.py",
            "test_outcome_evaluator_closed_identity_v1.py",
            "test_trade_close_outcome_semantic_recurrence_v1.py",
            "test_trade_lifecycle_shadow_storage_guard_v1.py",
        )
    elif sys.argv[1:] == ["--paper-integrated-disk-guard-no-flask"]:
        cases = (
            "test_paper_executor_integrated_idempotency_v1.py",
            "test_paper_executor_data_dir_resolution_v1.py",
            "test_execution_pipeline_status_paper_state_v1.py",
            "test_adaptive_weights_data_dir_guard_v1.py",
            "test_paper_state_storage_render_paths_v1.py",
            "test_main_paper_audit_storage_guard_v1.py",
            "test_runtime_file_lock_fail_closed_v1.py",
            "test_outcome_evaluator_closed_identity_v1.py",
            "test_trade_close_outcome_semantic_recurrence_v1.py",
            "test_trade_lifecycle_shadow_storage_guard_v1.py",
        )
    elif sys.argv[1:] == ["--paper-lifecycle-disk-failures"]:
        cases = ("test_timeline_single_writer.py",)
        filters = ["-k", "paper_lifecycle"]
    elif sys.argv[1:] == ["--paper-lifecycle-integration"]:
        cases = ("test_trade_lifecycle_shadow_runtime_adapter.py",)
        filters = ["-k", "not test_shadow_validation_append_is_idempotent_across_processes"]
    elif sys.argv[1:] == ["--static-runtime"]:
        cases = ("test_static_operational_runtime_v1.py",)
    elif sys.argv[1:] == ["--predator-auto-closed-sync"]:
        cases = ("test_predator_auto_closed_registry_sync.py",)
    elif sys.argv[1:] == ["--trading-mode-defaults"]:
        cases = ("test_trading_mode_defaults_fail_closed_v1.py",)
    elif sys.argv[1:] == ["--personal-http-auth"]:
        cases = (
            "test_personal_http_auth_gate_v1.py",
            "test_personal_thread_diagnostics.py",
            "test_falcon_central_only_reconciliation.py",
            "test_falcon_manual_close_outcome_reconciliation_v1.py",
        )
    elif sys.argv[1:] == ["--learning-cursor-guard"]:
        cases = ("test_executive_policy_learning_cursor_guard_v1.py",)
    elif sys.argv[1:] == ["--telegram-notification-policy"]:
        cases = ("test_telegram_notification_policy.py",)
    elif sys.argv[1:] == ["--persistence-locks"]:
        cases = (
            "test_trade_registry_atomic_durable_write_v1.py",
            "test_trade_registry_reset_serialization_v1.py",
            "test_runtime_file_lock_fail_closed_v1.py",
            "test_main_runtime_drain_contract_v1.py",
        )
    elif sys.argv[1:] == ["--registry-startup-admission"]:
        cases = ("test_main_runtime_drain_contract_v1.py",)
    elif sys.argv[1:] == ["--personal-execution-safety"]:
        cases = (
            "test_falcon_real_pilot_preflight_fail_closed_v1.py",
            "test_falcon_initial_stop_failure_containment_v1.py",
            "test_broker_managed_entry_cancel_v1.py",
            "test_broker_entry_fill_stop_sizing_v1.py",
            "test_falcon_management_safety_v1.py",
            "test_account_client_order_writer_contract_v1.py",
            "test_bingx_ccxt_stop_readback_contract_v1.py",
            "test_real_close_reconciliation_v11.py",
            "test_broker_finite_numeric_inputs_v1.py",
            "test_falcon_positions_read_fail_closed_v1.py",
            "test_live_central_risk_gate_fail_closed_v1.py",
            "test_live_position_reconciliation_risk_gate_v1.py",
            "test_disaster_stop_fallback_route_auth_v1.py",
            "test_auto_real_execution_bridge_route_auth_v1.py",
        )
    elif sys.argv[1:] == ["--personal-lifecycle-completeness"]:
        cases = (
            "test_broker_entry_fill_stop_sizing_v1.py",
            "test_broker_managed_entry_cancel_v1.py",
            "test_broker_managed_close_timeout_semantics_v1.py",
            "test_personal_bot_positions_read_fail_closed_v1.py",
            "test_falcon_initial_stop_failure_containment_v1.py",
            "test_falcon_disaster_stop_failure_forensics_v1.py",
            "test_falcon_terminal_disaster_stop_emergency_recovery_v1.py",
            "test_falcon_positions_read_fail_closed_v1.py",
            "test_falcon_central_only_reconciliation.py",
            "test_falcon_manual_close_outcome_reconciliation_v1.py",
            "test_real_close_reconciliation_v11.py",
            "test_real_trade_lifecycle_missing_from_bots_close_v1.py",
            "test_live_position_reconciliation_risk_gate_v1.py",
        )
    elif sys.argv[1:] == ["--personal-lifecycle-no-ccxt"]:
        # Preserve an explicit offline lifecycle subset when ccxt is not
        # installed. The three omitted broker modules are not represented as
        # tested by this selection and remain covered only by the full mode.
        cases = (
            "test_broker_managed_close_timeout_semantics_v1.py",
            "test_personal_bot_positions_read_fail_closed_v1.py",
            "test_falcon_initial_stop_failure_containment_v1.py",
            "test_falcon_disaster_stop_failure_forensics_v1.py",
            "test_falcon_terminal_disaster_stop_emergency_recovery_v1.py",
            "test_falcon_positions_read_fail_closed_v1.py",
            "test_falcon_central_only_reconciliation.py",
            "test_falcon_manual_close_outcome_reconciliation_v1.py",
            "test_real_trade_lifecycle_missing_from_bots_close_v1.py",
            "test_live_position_reconciliation_risk_gate_v1.py",
        )
    elif sys.argv[1:] == ["--personal-position-read-fail-closed"]:
        cases = ("test_personal_bot_positions_read_fail_closed_v1.py",)
    elif sys.argv[1:] == ["--falcon-lifecycle-projection"]:
        cases = ("test_falcon_lifecycle_observation_projection.py",)
    elif sys.argv[1:] == ["--upstash-sdk-contract"]:
        cases = (
            "test_account_client_order_id_v1.py",
            "test_personal_bot_positions_read_fail_closed_v1.py",
        )
    elif sys.argv[1:] == ["--account-client-order-authority"]:
        cases = ("test_account_client_order_id_v1.py",)
    elif sys.argv[1:] == ["--personal-safety-no-ccxt"]:
        # Run the available personal-execution regressions when the offline
        # Python environment has no cached ccxt package. The ccxt-dependent
        # modules are not silently represented as tested by this selection.
        cases = (
            "test_falcon_real_pilot_preflight_fail_closed_v1.py",
            "test_falcon_initial_stop_failure_containment_v1.py",
            "test_falcon_management_safety_v1.py",
            "test_account_client_order_writer_contract_v1.py",
            "test_falcon_positions_read_fail_closed_v1.py",
            "test_live_central_risk_gate_fail_closed_v1.py",
            "test_live_position_reconciliation_risk_gate_v1.py",
            "test_disaster_stop_fallback_route_auth_v1.py",
            "test_auto_real_execution_bridge_route_auth_v1.py",
            "test_trading_mode_defaults_fail_closed_v1.py",
        )
    elif sys.argv[1:] == ["--stop-readback"]:
        cases = ("test_falcon_client_order_id_collision_guard_v1.py",)
    elif sys.argv[1:] == ["--finite-numeric"]:
        cases = ("test_broker_finite_numeric_inputs_v1.py",)
    elif sys.argv[1:] == ["--close-reconciliation"]:
        cases = ("test_real_close_reconciliation_v11.py",)
    elif sys.argv[1:] == ["--initial-stop-containment"]:
        cases = (
            "test_falcon_initial_stop_failure_containment_v1.py",
            "test_broker_managed_entry_cancel_v1.py",
        )
    elif sys.argv[1:] == ["--initial-stop-cancel"]:
        cases = (
            "test_falcon_initial_stop_failure_containment_v1.py",
            "test_broker_entry_fill_stop_sizing_v1.py",
        )
    elif sys.argv[1:] == ["--entry-fill-stop"]:
        cases = (
            "test_broker_account_client_order_boundary_v1.py",
            "test_broker_entry_fill_stop_sizing_v1.py",
        )
    elif sys.argv[1:] == ["--preflight-storage-readiness"]:
        cases = ("test_falcon_real_pilot_preflight_fail_closed_v1.py",)
    else:
        cases = CASES
    if sys.argv[1:] == ["--registry-lock-audit"]:
        filters = ["-k", "test_every_direct_registry_save_call_is_inside_shared_lock"]
    elif sys.argv[1:] == ["--registry-writers"]:
        filters = []
    elif sys.argv[1:] == ["--registry-sync"]:
        filters = []
    elif sys.argv[1:] == ["--registry-v2-migration-audit"]:
        filters = []
    elif sys.argv[1:] == ["--paper-registry-source-preview"]:
        filters = []
    elif sys.argv[1:] == ["--paper-registry-source-capture"]:
        filters = []
    elif sys.argv[1:] == ["--history-memory-state-io"]:
        filters = []
    elif sys.argv[1:] == ["--history-storage-serialization"]:
        filters = ["-k", "history_manager_prefers_central_data_dir_and_uses_guarded_basic_io"]
    elif sys.argv[1:] == ["--history-render-rewrite-guard"]:
        filters = []
    elif sys.argv[1:] == ["--lifecycle-shadow-bridge-storage-guard"]:
        filters = []
    elif sys.argv[1:] == ["--central-runtime-lock-guard"]:
        filters = []
    elif sys.argv[1:] == ["--paper-main-storage-guard"]:
        filters = []
    elif sys.argv[1:] == ["--arb-tail-storage-guard"]:
        filters = []
    elif sys.argv[1:] == ["--data-status-lock-guard"]:
        filters = ["-k", "data_status_lock_inventory_uses_guarded_listing"]
    elif sys.argv[1:] == ["--policy-storage-guard"]:
        filters = []
    elif sys.argv[1:] == ["--journal-learning-storage-guard"]:
        filters = []
    elif sys.argv[1:] == ["--memory-profiler-storage-guard"]:
        filters = []
    elif sys.argv[1:] == ["--paper-integrated-disk-guard-no-flask"]:
        filters = ["-k", "not test_daily_history_blocks_ephemeral_render_fallback"]
    elif sys.argv[1:] == ["--preflight-storage-readiness"]:
        filters = ["-k", "preflight_storage_real_status or live_entry_storage_readiness_fails_closed_without_process_lock"]
    elif sys.argv[1:] == ["--can-open-risk"]:
        filters = [
            "-k",
            "reduce_only_claim or registry_sync_fails or does_not_block_paper or "
            "auto_bridge_blocks_every_invalid_falcon_can_open_contract or "
            "can_open_trade_wrapper_attaches_only_validated_falcon_bridge_suppression or "
            "can_open_trade_bridge_requires_all_runtime_live_controls",
        ]
    elif sys.argv[1:] == ["--c3-dormant-startup"]:
        filters = []
    elif sys.argv[1:] == ["--c3-dormant-startup-verbose"]:
        filters = []
    elif sys.argv[1:] == ["--market-data-throttle"]:
        filters = []
    elif sys.argv[1:] == ["--broker-paper-disk-guard"]:
        filters = []
    elif sys.argv[1:] == ["--broker-log-storage-guard"]:
        filters = []
    elif sys.argv[1:] == ["--registry-v2-paper-storage-guard"]:
        filters = []
    elif sys.argv[1:] == ["--paper-integrated-disk-guard"]:
        filters = []
    elif sys.argv[1:] == ["--paper-lifecycle-disk-failures"]:
        filters = ["-k", "paper_lifecycle"]
    elif sys.argv[1:] == ["--paper-lifecycle-integration"]:
        filters = ["-k", "not test_shadow_validation_append_is_idempotent_across_processes"]
    elif sys.argv[1:] == ["--static-runtime"]:
        filters = []
    elif sys.argv[1:] == ["--predator-auto-closed-sync"]:
        filters = []
    elif sys.argv[1:] == ["--trading-mode-defaults"]:
        filters = []
    elif sys.argv[1:] == ["--personal-http-auth"]:
        filters = []
    elif sys.argv[1:] == ["--learning-cursor-guard"]:
        filters = []
    elif sys.argv[1:] == ["--telegram-notification-policy"]:
        filters = []
    elif sys.argv[1:] == ["--persistence-locks"]:
        filters = []
    elif sys.argv[1:] == ["--registry-startup-admission"]:
        filters = ["-k", "persistent_registry_startup_admission_requires_mount_file_and_schema"]
    elif sys.argv[1:] == ["--personal-execution-safety"]:
        filters = []
    elif sys.argv[1:] == ["--personal-lifecycle-completeness"]:
        filters = []
    elif sys.argv[1:] == ["--personal-lifecycle-no-ccxt"]:
        filters = []
    elif sys.argv[1:] == ["--falcon-lifecycle-projection"]:
        filters = []
    elif sys.argv[1:] == ["--upstash-sdk-contract"]:
        filters = [
            "-k",
            "test_default_redis_client_bounds_real_upstash_get_without_network or "
            "test_upstash_httpx_redis_get_timeout_with_mock_transport",
        ]
    elif sys.argv[1:] == ["--account-client-order-authority"]:
        filters = []
    elif sys.argv[1:] == ["--personal-safety-no-ccxt"]:
        filters = []
    elif sys.argv[1:] == ["--stop-readback"]:
        filters = []
    elif sys.argv[1:] == ["--finite-numeric"]:
        filters = []
    elif sys.argv[1:] == ["--close-reconciliation"]:
        filters = []
    elif sys.argv[1:] == ["--initial-stop-containment"]:
        filters = []
    elif sys.argv[1:] == ["--initial-stop-cancel"]:
        filters = []
    elif sys.argv[1:] == ["--entry-fill-stop"]:
        filters = []
    else:
        filters = ["-k", "not test_shadow_validation_append_is_idempotent_across_processes"] if cases is EXTRA_CASES else []
    if sys.argv[1:] == ["--history-memory-state-io"]:
        # The suite runner forbids subprocess creation; this test's isolated
        # child-process import check is exercised separately outside the runner.
        filters.extend(["-k", "not test_no_test_uses_real_data_network_redis_or_broker"])
    pytest_args = [
        "-vv" if sys.argv[1:] == ["--c3-dormant-startup-verbose"] else "-q",
        "-p",
        "no:cacheprovider",
    ]
    # The unittest-based C3 startup integration tests use pytest's trace-option
    # lookup in pytest's unittest adapter, so keep the built-in debugging
    # plugin registered for this focused mode (the option remains false).
    if sys.argv[1:] not in (
        ["--c3-dormant-startup"],
        ["--c3-dormant-startup-verbose"],
        ["--can-open-risk"],
        ["--paper-integrated-disk-guard"],
        ["--paper-integrated-disk-guard-no-flask"],
        ["--policy-storage-guard"],
    ):
        pytest_args.extend(["-p", "no:debugging"])
    raise SystemExit(
        pytest.main(
            [
                *pytest_args,
                *filters,
                *(str(ROOT / "tests" / name) for name in cases),
            ]
        )
    )
