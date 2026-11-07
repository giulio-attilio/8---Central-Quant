import ast
import threading
from pathlib import Path

import pytest
from runtime_drain_v1 import RuntimeDrainState


ROOT = Path(__file__).resolve().parents[1]


def _source(path):
    return path.read_text(encoding="utf-8")


def _decorator_names(node):
    return {
        item.func.id
        if isinstance(item, ast.Call) and isinstance(item.func, ast.Name)
        else item.id
        if isinstance(item, ast.Name)
        else None
        for item in node.decorator_list
    }


def test_broker_public_market_entry_is_wrapped_at_the_final_boundary():
    tree = ast.parse(_source(ROOT / "broker.py"))
    target = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "place_market_order"
    )
    assert "guard_new_live_entries" in _decorator_names(target)


def test_main_final_engine_wrapper_tracks_the_complete_live_flow():
    tree = ast.parse(_source(ROOT / "main.py"))
    providers = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "run_execution_engine"
    ]
    assert providers
    assert "guard_live_flow" in _decorator_names(providers[-1])


def test_falcon_scanner_holds_drain_lease_through_accepted_signal_persistence():
    tree = ast.parse(_source(ROOT / "bots" / "falcon.py"))
    process = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_falcon_process_entry_signal"
    )
    assert "guard_live_flow" in _decorator_names(process)
    process_calls = {
        node.func.id
        for node in ast.walk(process)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "falcon_persist_accepted_signal" in process_calls
    scanner = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "scanner_loop"
    )
    assert "_falcon_process_entry_signal" in {
        node.func.id
        for node in ast.walk(scanner)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def test_final_falcon_management_loop_drains_only_between_full_cycles():
    tree = ast.parse(_source(ROOT / "bots" / "falcon.py"))
    providers = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "management_loop"
    ]
    assert providers
    target = providers[-1]
    calls = [
        node.func.attr
        for node in ast.walk(target)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "try_enter_management_cycle" in calls
    assert "leave_management_cycle" in calls
    assert "is_draining" in calls
    assert any(
        isinstance(node, ast.Try) and node.finalbody
        and any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "leave_management_cycle"
            for stmt in node.finalbody
            for child in ast.walk(stmt)
        )
        for node in ast.walk(target)
    )


def test_runtime_startup_rejects_failed_persistent_registry_admission_before_bots():
    tree = ast.parse(_source(ROOT / "main.py"))
    start = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "start_central_runtime_once"
    )
    namespace = {
        "CENTRAL_RUNTIME_LOCK": threading.RLock(),
        "CENTRAL_RUNTIME_STARTED": False,
        "LEARNING_AUTO_REFRESH_THREAD_STARTED": False,
        "CENTRAL_DAILY_REPORT_THREAD_STARTED": False,
        "CENTRAL_DAILY_REPORT_LAST_STATUS": None,
        "C3_MAINTENANCE_STARTUP_BINDING_V1": None,
        "_central_persistent_registry_startup_admission_v1": lambda: {
            "ok": False,
            "status": "PERSISTENT_TRADE_REGISTRY_MISSING",
        },
        "start_enabled_bots": lambda: bot_starts.append(True),
    }
    bot_starts = []
    exec(compile(ast.Module(body=[start], type_ignores=[]), "main.py", "exec"), namespace)

    with pytest.raises(RuntimeError, match="PERSISTENT_TRADE_REGISTRY_MISSING"):
        namespace["start_central_runtime_once"]()

    assert bot_starts == []
    assert namespace["CENTRAL_RUNTIME_STARTED"] is False


def test_runtime_readiness_is_published_only_after_bot_and_router_startup():
    tree = ast.parse(_source(ROOT / "main.py"))
    start = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "start_central_runtime_once"
    )
    ready_assignments = [
        node for node in ast.walk(start)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "CENTRAL_RUNTIME_READY"
            for target in node.targets
        )
    ]
    assert len(ready_assignments) == 1
    ready_line = ready_assignments[0].lineno
    bot_start_lines = [
        node.lineno for node in ast.walk(start)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "start_enabled_bots"
    ]
    router_start_lines = [
        node.lineno for node in ast.walk(start)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "start_central_command_routers"
    ]
    assert bot_start_lines and router_start_lines
    assert ready_line > max(bot_start_lines + router_start_lines)


def test_runtime_readiness_requires_every_enabled_bot_to_be_loaded_and_started():
    tree = ast.parse(_source(ROOT / "main.py"))
    start = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "start_central_runtime_once"
    )
    ready_assignment = next(
        node for node in ast.walk(start)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "CENTRAL_RUNTIME_READY"
            for target in node.targets
        )
    )
    ready_expression = compile(ast.Expression(ready_assignment.value), "main.py", "eval")
    enabled = {"ENABLE_TRENDPRO": True, "ENABLE_DONKEY": False}
    namespace = {
        "env_bool": lambda key, default=False: enabled.get(key, default),
        "BOT_CONFIGS": {
            "TRENDPRO": {"enabled_env": "ENABLE_TRENDPRO"},
            "DONKEY": {"enabled_env": "ENABLE_DONKEY"},
        },
        "LOADED_BOTS": {},
        "BOT_THREADS_STARTED": set(),
    }

    assert eval(ready_expression, namespace) is False
    namespace["LOADED_BOTS"]["TRENDPRO"] = object()
    assert eval(ready_expression, namespace) is False
    namespace["BOT_THREADS_STARTED"].add("TRENDPRO")
    assert eval(ready_expression, namespace) is True

    enabled["ENABLE_TRENDPRO"] = False
    namespace["LOADED_BOTS"].clear()
    namespace["BOT_THREADS_STARTED"].clear()
    assert eval(ready_expression, namespace) is True


def test_bot_import_defers_worker_start_until_explicit_central_hook():
    bot_files = (
        "trendpro.py",
        "donkey.py",
        "cobra.py",
        "meme.py",
        "predator.py",
        "turtle.py",
        "falcon.py",
    )
    for filename in bot_files:
        tree = ast.parse(_source(ROOT / "bots" / filename))
        assert any(
            isinstance(node, ast.FunctionDef)
            and node.name == "start_central_bot_threads"
            for node in tree.body
        ), filename
        guarded_start = any(
            isinstance(node, ast.If)
            and any(
                isinstance(child, ast.Constant)
                and child.value == "CENTRAL_DEFER_BOT_STARTUP"
                for child in ast.walk(node.test)
            )
            and any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "start_central_bot_threads"
                for stmt in node.body
                for child in ast.walk(stmt)
            )
            for node in tree.body
        )
        assert guarded_start, filename


def test_main_imports_all_enabled_bots_before_invoking_any_worker_hook():
    tree = ast.parse(_source(ROOT / "main.py"))
    start = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "start_enabled_bots"
    )
    load_lines = [
        node.lineno
        for node in ast.walk(start)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "load_bot"
    ]
    worker_lines = [
        node.lineno
        for node in ast.walk(start)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "starter"
    ]
    missing_gate_lines = [
        node.lineno
        for node in ast.walk(start)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_central_missing_enabled_bot_modules"
    ]
    assert load_lines and worker_lines and missing_gate_lines
    assert max(load_lines) < min(worker_lines)
    assert max(load_lines) < min(missing_gate_lines) < min(worker_lines)


def test_enabled_import_failure_blocks_worker_launch():
    tree = ast.parse(_source(ROOT / "main.py"))
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_central_missing_enabled_bot_modules"
    )
    enabled = {"ENABLE_TRENDPRO": True, "ENABLE_DONKEY": False}
    namespace = {
        "BOT_CONFIGS": {
            "TRENDPRO": {"enabled_env": "ENABLE_TRENDPRO"},
            "DONKEY": {"enabled_env": "ENABLE_DONKEY"},
        },
        "LOADED_BOTS": {},
        "env_bool": lambda key, default=False: enabled.get(key, default),
    }
    exec(compile(ast.Module(body=[helper], type_ignores=[]), "main.py", "exec"), namespace)
    assert namespace["_central_missing_enabled_bot_modules"]() == ["TRENDPRO"]
    namespace["LOADED_BOTS"]["TRENDPRO"] = object()
    assert namespace["_central_missing_enabled_bot_modules"]() == []


def test_persistent_registry_startup_admission_requires_mount_file_and_schema():
    tree = ast.parse(_source(ROOT / "main.py"))
    gate = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_central_persistent_registry_startup_admission_v1"
    )

    class FakePath:
        mount_available = False
        file_available = False

        def __init__(self, value):
            self.value = str(value)

        def __str__(self):
            return self.value

        def is_mount(self):
            return self.mount_available

        def is_file(self):
            return self.file_available

    registry = {"version": "synthetic-v1", "open_trades": {}, "closed_trades": []}
    namespace = {
        "Path": FakePath,
        "os": type("PosixOs", (), {"name": "posix"}),
        "_trpsf_v1_active_file": lambda: "/data/trade_registry.json",
        "_trpsf_v1_read_json": lambda _path: registry,
        "_trpsf_v1_registry_shape_errors": lambda _registry: [],
    }
    exec(compile(ast.Module(body=[gate], type_ignores=[]), "main.py", "exec"), namespace)
    admission = namespace["_central_persistent_registry_startup_admission_v1"]

    assert admission()["status"] == "PERSISTENT_DATA_MOUNT_NOT_VERIFIED"

    FakePath.mount_available = True
    assert admission()["status"] == "PERSISTENT_TRADE_REGISTRY_MISSING"

    FakePath.file_available = True
    assert admission()["status"] == "PERSISTENT_TRADE_REGISTRY_READY"

    namespace["_trpsf_v1_registry_shape_errors"] = lambda _registry: ["OPEN_TRADES_INVALID_SHAPE"]
    assert admission()["status"] == "PERSISTENT_TRADE_REGISTRY_INVALID_SHAPE"


def test_predator_entry_flow_tracks_post_broker_lifecycle_updates():
    tree = ast.parse(_source(ROOT / "bots" / "predator.py"))
    target = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "execute_predator_signal_safe"
    )
    assert "guard_live_flow" in _decorator_names(target)


def test_final_admission_provider_denies_new_live_entries_during_drain():
    tree = ast.parse(_source(ROOT / "main.py"))
    providers = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "can_open_trade_decision"
    ]
    assert providers
    final_provider = providers[-1]
    calls = [
        node.func.attr
        for node in ast.walk(final_provider)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "is_draining" in calls
    assert "ENTRY_BLOCKED_RUNTIME_DRAIN" in ast.unparse(final_provider)


def test_loaded_central_admission_provider_returns_deny_during_drain():
    import main

    original_drain = main.RUNTIME_DRAIN
    original_append = main.append_decision_log
    state = RuntimeDrainState()
    state.begin_draining()
    main.RUNTIME_DRAIN = state
    main.append_decision_log = lambda *_args, **_kwargs: None
    try:
        result = main.can_open_trade_decision({
            "bot": "FALCON",
            "symbol": "BTCUSDT",
            "side": "LONG",
            "mode": "LIVE",
            "reduce_only": False,
        })
    finally:
        main.RUNTIME_DRAIN = original_drain
        main.append_decision_log = original_append
    assert result["allowed"] is False
    assert result["decision"] == "DENY"
    assert result["status"] == "ENTRY_BLOCKED_RUNTIME_DRAIN"
    assert result["reasons"] == ["RUNTIME_DRAINING"]


def test_http_server_starts_before_runtime_boot_and_shutdown_remains_bounded():
    source = _source(ROOT / "main.py")
    install = source.index("install_shutdown_signal_handlers(")
    serve_target = source.index("target=_central_shutdown_server.serve_forever")
    serve_start = source.index("_central_http_server_thread.start()")
    startup = source.index("if CENTRAL_AUTO_START_RUNTIME:")
    join = source.index("_central_http_server_thread.join()")
    assert install < serve_target < serve_start < startup < join
    assert "threaded=True" in source[install - 180 : serve_target]
    assert "daemon=True" in source[serve_target:serve_start]
    assert "grace_seconds=27.0" in source[join:]
    assert "server.shutdown" not in source[join:]


def test_bot_startup_logs_bracket_import_and_history_wrap_without_environment_values():
    source = _source(ROOT / "main.py")
    start = source.index("def start_enabled_bots():")
    end = source.index("\ndef bot_health(", start)
    block = source[start:end]
    markers = (
        "BOT STARTUP LOAD BEGIN",
        "load_bot(key, cfg)",
        "BOT STARTUP IMPORT COMPLETE",
        "BOT STARTUP HISTORY WRAP BEGIN",
        "wrap_bot_module(LOADED_BOTS[key], key)",
        "BOT STARTUP HISTORY WRAP COMPLETE",
    )
    positions = [block.index(marker) for marker in markers]
    assert positions == sorted(positions)
    assert "TOKEN" not in block
    assert "CHAT_ID" not in block


def test_drain_is_process_local_and_never_changes_trading_mode_controls():
    source = _source(ROOT / "runtime_drain_v1.py")
    assert "RUNTIME_DRAIN = RuntimeDrainState()" in source
    assert "import socket" not in source
    assert "urllib" not in source
    assert "ENABLE_REAL_TRADING" not in source
    assert "BROKER_DRY_RUN" not in source
    assert "FALCON_MODE" not in source
