"""Run the existing Falcon safety regressions without external access.

Usage: python3 -I tests/run_falcon_pilot_minimal_offline.py
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
        cases = ("test_registry_remaining_writers_atomic_rmw_v1.py",)
    elif sys.argv[1:] == ["--registry-sync"]:
        cases = ("test_main_traderegistry_sync_v2_ownership.py",)
    elif sys.argv[1:] == ["--can-open-risk"]:
        cases = (
            "test_history_eventbus_smoke.py",
            "test_falcon_single_live_execution_path_v1.py",
        )
    elif sys.argv[1:] == ["--c3-dormant-startup"]:
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
    elif sys.argv[1:] == ["--paper-integrated-disk-guard"]:
        cases = ("test_paper_executor_integrated_idempotency_v1.py",)
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
            "test_falcon_central_only_reconciliation.py",
            "test_falcon_manual_close_outcome_reconciliation_v1.py",
        )
    elif sys.argv[1:] == ["--persistence-locks"]:
        cases = (
            "test_trade_registry_atomic_durable_write_v1.py",
            "test_trade_registry_reset_serialization_v1.py",
            "test_runtime_file_lock_fail_closed_v1.py",
            "test_main_runtime_drain_contract_v1.py",
        )
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
    elif sys.argv[1:] == ["--personal-safety-no-ccxt"]:
        # Run the available personal-execution regressions when the offline
        # Python environment has no cached ccxt package. The two excluded
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
    else:
        cases = CASES
    if sys.argv[1:] == ["--registry-lock-audit"]:
        filters = ["-k", "test_every_direct_registry_save_call_is_inside_shared_lock"]
    elif sys.argv[1:] == ["--registry-writers"]:
        filters = []
    elif sys.argv[1:] == ["--registry-sync"]:
        filters = []
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
    elif sys.argv[1:] == ["--market-data-throttle"]:
        filters = []
    elif sys.argv[1:] == ["--broker-paper-disk-guard"]:
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
    elif sys.argv[1:] == ["--persistence-locks"]:
        filters = []
    elif sys.argv[1:] == ["--personal-execution-safety"]:
        filters = []
    elif sys.argv[1:] == ["--personal-lifecycle-completeness"]:
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
    pytest_args = ["-q", "-p", "no:cacheprovider"]
    # The unittest-based C3 startup integration tests use pytest's trace-option
    # lookup in pytest's unittest adapter, so keep the built-in debugging
    # plugin registered for this focused mode (the option remains false).
    if sys.argv[1:] not in (
        ["--c3-dormant-startup"],
        ["--can-open-risk"],
        ["--paper-integrated-disk-guard"],
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
